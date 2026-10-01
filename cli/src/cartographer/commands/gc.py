"""`cartographer gc`: remove tombstoned artifacts from the central index.

Deletes VDB chunks and KG nodes that were tombstoned more than `--older-than` days
ago. Default retention is 30 days. Use `--older-than 0` to delete immediately.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod
from cartographer.indexing.central import get_central_kg, get_central_vdb

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be deleted without writing anything."),
    older_than: int = typer.Option(30, "--older-than", help="Delete tombstones older than this many days (0 = delete immediately)."),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    cfg = config_mod.load_config(workspace)

    if cfg.topology.mode == "local":
        console.print("topology is local-only; nothing to gc")
        raise typer.Exit(code=0)

    override = config_mod.load_local_override(workspace)

    try:
        central_vdb = get_central_vdb(cfg, override)
        central_kg = get_central_kg(cfg, override)
    except (ValueError, NotImplementedError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if not central_vdb.is_reachable():
        console.print("[red]central VDB (pgvector) is not reachable[/red]")
        raise typer.Exit(code=1)

    if not central_kg.is_reachable():
        console.print("[red]central KG (Neo4j) is not reachable[/red]")
        raise typer.Exit(code=1)

    project_id = cfg.project.id
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=older_than)
    cutoff_iso = cutoff.isoformat()

    console.print("[bold]cartographer gc[/bold]")
    console.print(f"  project:    {project_id}")
    console.print(f"  older-than: {older_than} day(s) (cutoff: {cutoff_iso})")

    # Collect tombstoned VDB chunks older than the cutoff
    vdb_paths = _collect_tombstoned_vdb_paths(central_vdb, project_id, cutoff_iso)

    # Collect tombstoned KG nodes older than the cutoff
    kg_node_ids = _collect_tombstoned_kg_node_ids(central_kg, cutoff_iso)

    console.print(f"  vdb paths:  {len(vdb_paths)} path(s) eligible")
    console.print(f"  kg nodes:   {len(kg_node_ids)} node(s) eligible")

    if dry_run:
        console.print("[yellow]--dry-run: no changes written[/yellow]")
        for p in sorted(vdb_paths):
            console.print(f"  [vdb] would delete: {p}")
        for nid in sorted(kg_node_ids):
            console.print(f"  [kg]  would delete: {nid}")
        raise typer.Exit(code=0)

    if not vdb_paths and not kg_node_ids:
        console.print("nothing to collect (no eligible tombstones)")
        raise typer.Exit(code=0)

    # Delete tombstoned VDB chunks
    vdb_deleted = 0
    for p in vdb_paths:
        try:
            _delete_tombstoned_vdb_path(central_vdb, project_id, p)
            vdb_deleted += 1
        except Exception as exc:
            console.print(f"[yellow]warning: failed to delete VDB path {p}: {exc}[/yellow]")

    # Delete tombstoned KG nodes
    kg_deleted = 0
    if kg_node_ids:
        try:
            central_kg.delete_nodes(list(kg_node_ids))
            kg_deleted = len(kg_node_ids)
        except Exception as exc:
            console.print(f"[yellow]warning: failed to delete KG nodes: {exc}[/yellow]")

    console.print(f"  deleted:    {vdb_deleted} vdb path(s), {kg_deleted} kg node(s)")
    console.print("[bold green]gc complete[/bold green]")


def _collect_tombstoned_vdb_paths(central_vdb, project_id: str, cutoff_iso: str) -> set[str]:
    """Return distinct paths of tombstoned chunks updated before the cutoff."""
    try:
        from cartographer.indexing.vdb_pgvector import _table_name
        table = _table_name(project_id)
        conn = central_vdb._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT DISTINCT path FROM {table} "
                    f"WHERE is_tombstone = TRUE AND updated_at < %s",
                    (cutoff_iso,),
                )
                return {row[0] for row in cur.fetchall()}
        except Exception:
            return set()
        finally:
            conn.close()
    except Exception:
        return set()


def _delete_tombstoned_vdb_path(central_vdb, project_id: str, path: str) -> None:
    """Hard-delete all tombstoned chunks for the given path."""
    from cartographer.indexing.vdb_pgvector import _table_name
    table = _table_name(project_id)
    conn = central_vdb._connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {table} WHERE path = %s AND is_tombstone = TRUE",
                    (path,),
                )
    finally:
        conn.close()


def _collect_tombstoned_kg_node_ids(central_kg, cutoff_iso: str) -> set[str]:
    """Return IDs of KG nodes whose tombstoned_at timestamp is before the cutoff."""
    try:
        rows = central_kg.query(
            "MATCH (a:Artifact) "
            "WHERE a.tombstoned_at IS NOT NULL AND a.tombstoned_at <> '' "
            "AND a.tombstoned_at < $cutoff "
            "RETURN a.id AS id",
            {"cutoff": cutoff_iso},
        )
        return {row["id"] for row in rows}
    except Exception:
        return set()
