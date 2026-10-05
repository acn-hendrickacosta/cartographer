"""`cartographer promote`: promote merged local artifacts to the central global index.

Reads all chunks from the local LanceDB and all nodes/edges from the local Kuzu,
then upserts them into the central pgvector and Neo4j backends under the global scope.
Idempotent: all upserts are keyed on artifact identity.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from cartographer import config as config_mod, registry
from cartographer.artifact_id import artifact_id
from cartographer.indexing import kg as kg_driver, vdb as vdb_driver
from cartographer.indexing.central import get_central_kg, get_central_vdb
from cartographer.indexing.vdb import ChunkRecord
from cartographer.indexing.kg import Node, Edge

console = Console()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
    full: bool = typer.Option(False, "--full/--incremental", help="Promote all local artifacts (--full) or only those changed since last promotion (--incremental, default)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be promoted without writing anything."),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    cfg = config_mod.load_config(workspace)

    if cfg.topology.mode == "local":
        console.print("topology is local-only; nothing to promote")
        raise typer.Exit(code=0)

    override = config_mod.load_local_override(workspace)

    if not override.promotion_token:
        console.print(
            "[red]promotion_token not set in .cartographer.local.toml[/red]\n"
            "Run 'cartographer init' with topology.mode = 'central' to generate one."
        )
        raise typer.Exit(code=1)

    # Verify central backends are reachable
    try:
        central_vdb = get_central_vdb(cfg, override)
        central_kg = get_central_kg(cfg, override)
    except (ValueError, NotImplementedError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if not central_vdb.is_reachable():
        console.print("[red]central VDB (pgvector) is not reachable; check .cartographer.local.toml[/red]")
        raise typer.Exit(code=1)

    if not central_kg.is_reachable():
        console.print("[red]central KG (Neo4j) is not reachable; check .cartographer.local.toml[/red]")
        raise typer.Exit(code=1)

    local_dir = workspace / ".cartographer" / "local"
    vdb_path = local_dir / "vdb.lance"
    kg_path = local_dir / "kg.kuzu"

    project_id = cfg.project.id
    record = registry.get_project(project_id)
    last_promoted_at = record.last_promoted_at if record else ""

    # Determine promotion mode
    incremental = not full and bool(last_promoted_at)

    console.print("[bold]cartographer promote[/bold]")
    console.print(f"  project:  {project_id}")
    console.print(f"  mode:     {'full' if full or not last_promoted_at else 'incremental'}")
    if incremental:
        console.print(f"  since:    {last_promoted_at}")

    # Read all local VDB chunks
    try:
        import lancedb
        db = lancedb.connect(str(vdb_path))
        tables = db.list_tables().tables if hasattr(db.list_tables(), "tables") else db.list_tables()
        all_chunks: list[ChunkRecord] = []
        for table_name in tables:
            tbl = db.open_table(table_name)
            for row in tbl.to_arrow().to_pylist():
                all_chunks.append(ChunkRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    scope="global",
                    artifact_type=row["artifact_type"],
                    path=row["path"],
                    symbol=row.get("symbol"),
                    spec_id=row.get("spec_id"),
                    origin="local",
                    text=row["text"],
                    embedding=row["embedding"].tolist() if hasattr(row["embedding"], "tolist") else list(row["embedding"]),
                    updated_at=row["updated_at"],
                ))
    except Exception as exc:
        console.print(f"[red]failed to read local VDB: {exc}[/red]")
        raise typer.Exit(code=1)

    # Read all local KG nodes and edges
    try:
        all_nodes_raw = kg_driver.query(kg_path, "MATCH (a:Artifact) RETURN a.id AS id, a.project_id AS project_id, a.scope AS scope, a.type AS type, a.path AS path, a.attrs AS attrs")
        all_edges_raw = kg_driver.query(kg_path, "MATCH (s:Artifact)-[r:RelatesTo]->(d:Artifact) RETURN s.id AS src, d.id AS dst, r.type AS type, r.scope AS scope, r.attrs AS attrs")
        all_nodes = [Node(id=r["id"], project_id=r["project_id"], scope="global", type=r["type"], path=r["path"], attrs=r.get("attrs", "{}")) for r in all_nodes_raw]
        all_edges = [Edge(src=r["src"], dst=r["dst"], type=r["type"], scope="global", attrs=r.get("attrs", "{}")) for r in all_edges_raw]
    except Exception as exc:
        console.print(f"[red]failed to read local KG: {exc}[/red]")
        raise typer.Exit(code=1)

    # Apply incremental filter: only artifacts changed since last_promoted_at
    if incremental:
        cutoff = datetime.datetime.fromisoformat(last_promoted_at)
        all_chunks = [
            c for c in all_chunks
            if datetime.datetime.fromisoformat(c.updated_at) > cutoff
        ]
        changed_paths = {c.path for c in all_chunks}
        all_nodes = [n for n in all_nodes if n.path in changed_paths]
        changed_node_ids = {n.id for n in all_nodes}
        all_edges = [e for e in all_edges if e.src in changed_node_ids]

    # Rename detection: git diff since the last promoted SHA. Run before tombstone
    # detection so renames are correctly separated from pure deletions — a renamed
    # path gets a supersedes edge, not a plain tombstone.
    rename_map: dict[str, str] = {}
    last_sha = record.last_promoted_sha if record else ""
    if last_sha:
        try:
            output = subprocess.check_output(
                ["git", "diff", "--name-status", "--diff-filter=R", f"{last_sha}..HEAD"],
                cwd=workspace, text=True,
            )
            for line in output.splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0].startswith("R"):
                    rename_map[parts[1]] = parts[2]
        except Exception:
            console.print("[yellow]  git rename detection unavailable; renames treated as delete + add[/yellow]")

    # Tombstone detection: paths previously promoted but absent from local VDB
    local_paths = {c.path for c in all_chunks}
    try:
        global_paths = set(central_vdb.query_all_paths(project_id))
    except Exception as exc:
        console.print(f"[yellow]warning: could not read global paths for tombstone detection: {exc}[/yellow]")
        global_paths = set()
    deleted_paths = (global_paths - local_paths) - set(rename_map.keys())

    console.print(f"  chunks:   {len(all_chunks)}")
    console.print(f"  nodes:    {len(all_nodes)}")
    console.print(f"  edges:    {len(all_edges)}")
    if deleted_paths:
        console.print(f"  deleted:  {len(deleted_paths)} path(s) to tombstone")
        for p in sorted(deleted_paths):
            console.print(f"    - {p}")
    if rename_map:
        console.print(f"  renamed:  {len(rename_map)} path(s)")
        for old_p, new_p in sorted(rename_map.items()):
            console.print(f"    - {old_p} -> {new_p}")

    if dry_run:
        console.print("[yellow]--dry-run: no changes written[/yellow]")
        raise typer.Exit(code=0)

    if not all_chunks and not all_nodes:
        console.print("nothing to promote (index is up to date)")
        raise typer.Exit(code=0)

    # Promote VDB chunks in batches
    batch_size = 100
    batches = [all_chunks[i:i + batch_size] for i in range(0, len(all_chunks), batch_size)]

    embedding_dim = len(all_chunks[0].embedding) if all_chunks else 384
    central_vdb.ensure_collection(project_id, embedding_dim)
    central_kg.ensure_namespace()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        if all_chunks:
            vdb_task = progress.add_task("promoting chunks", total=len(all_chunks))
            for batch in batches:
                central_vdb.upsert(project_id, batch, embedding_dim)
                progress.advance(vdb_task, len(batch))

        if all_nodes:
            kg_task = progress.add_task("promoting nodes", total=len(all_nodes))
            central_kg.upsert_nodes(all_nodes)
            progress.advance(kg_task, len(all_nodes))

        if all_edges:
            edge_task = progress.add_task("promoting edges", total=len(all_edges))
            central_kg.upsert_edges(all_edges)
            progress.advance(edge_task, len(all_edges))

    # Write supersedes edges + tombstone old paths for detected renames
    if rename_map:
        now = _now()
        for old_path, new_path in rename_map.items():
            try:
                central_kg.upsert_edges([Edge(
                    src=artifact_id(new_path),
                    dst=artifact_id(old_path),
                    type="supersedes",
                    scope="global",
                    attrs=json.dumps({"renamed_from": old_path, "renamed_at": now}),
                )])
            except Exception as exc:
                console.print(f"[yellow]warning: failed to write supersedes edge for {old_path} -> {new_path}: {exc}[/yellow]")
            try:
                central_kg.set_tombstoned(old_path, now)
            except Exception as exc:
                console.print(f"[yellow]warning: failed to tombstone KG node {old_path}: {exc}[/yellow]")
            try:
                central_vdb.tombstone_path(project_id, old_path)
            except Exception as exc:
                console.print(f"[yellow]warning: failed to tombstone VDB path {old_path}: {exc}[/yellow]")
        console.print(f"  renamed:    {len(rename_map)} path(s) linked via supersedes")

    # Write tombstone records for deleted paths
    if deleted_paths:
        now = _now()
        for path in deleted_paths:
            try:
                central_vdb.tombstone_path(project_id, path)
            except Exception as exc:
                console.print(f"[yellow]warning: failed to tombstone VDB path {path}: {exc}[/yellow]")
            try:
                central_kg.set_tombstoned(path, now)
            except Exception as exc:
                console.print(f"[yellow]warning: failed to tombstone KG node {path}: {exc}[/yellow]")
        console.print(f"  tombstoned: {len(deleted_paths)} deleted path(s)")

    # Update last_promoted_at / last_promoted_sha in the registry
    if record:
        record.last_promoted_at = _now()
        try:
            record.last_promoted_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=workspace, text=True,
            ).strip()
        except Exception:
            pass  # non-git repo or git unavailable; leave as previous value
        registry.upsert_project(record)

    console.print(f"  promoted: {len(all_chunks)} chunks, {len(all_nodes)} nodes, {len(all_edges)} edges")
    console.print("[bold green]promote complete[/bold green]")
