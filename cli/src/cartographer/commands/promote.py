"""`cartographer promote`: promote merged local artifacts to the central global index.

Reads all chunks from the local LanceDB and all nodes/edges from the local Kuzu,
then upserts them into the central pgvector and Neo4j backends under the global scope.
Idempotent: all upserts are keyed on artifact identity.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from cartographer import config as config_mod, registry
from cartographer.indexing import kg as kg_driver, vdb as vdb_driver
from cartographer.indexing.central import get_central_kg, get_central_vdb
from cartographer.indexing.vdb import ChunkRecord
from cartographer.indexing.kg import Node, Edge

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
    full: bool = typer.Option(True, "--full/--incremental", help="Promote all local artifacts (default) or only those changed since last promotion."),
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

    # Read all local VDB chunks
    console.print("[bold]cartographer promote[/bold]")
    console.print(f"  project: {project_id}")

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

    console.print(f"  chunks to promote: {len(all_chunks)}")
    console.print(f"  nodes to promote:  {len(all_nodes)}")
    console.print(f"  edges to promote:  {len(all_edges)}")

    if dry_run:
        console.print("[yellow]--dry-run: no changes written[/yellow]")
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
        vdb_task = progress.add_task("promoting chunks", total=len(all_chunks))
        for batch in batches:
            central_vdb.upsert(project_id, batch, embedding_dim)
            progress.advance(vdb_task, len(batch))

        kg_task = progress.add_task("promoting nodes", total=len(all_nodes))
        central_kg.upsert_nodes(all_nodes)
        progress.advance(kg_task, len(all_nodes))

        edge_task = progress.add_task("promoting edges", total=len(all_edges))
        central_kg.upsert_edges(all_edges)
        progress.advance(edge_task, len(all_edges))

    # Update registry
    record = registry.get_project(project_id)
    if record:
        import datetime
        record.last_indexed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        registry.upsert_project(record)

    console.print(f"  promoted: {len(all_chunks)} chunks, {len(all_nodes)} nodes, {len(all_edges)} edges")
    console.print("[bold green]promote complete[/bold green]")
