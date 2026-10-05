"""`cartographer log`: list promotion history for a project.

Phase 4 graph versioning. Reads PromotionRecord nodes from the central KG
(Neo4j) — a separate, append-only history distinct from
registry.ProjectRecord.last_promoted_sha, which is a single value used as
Phase 3.3's rename-detection diff base, not a log.

Note: `at_commit` filtering on kg_query (reconstructing the graph as it
looked as of a specific past promotion) is not implemented. Doing that
safely would mean either a dedicated query tool with its own Cypher we
control, or tagging every Artifact node with the commit it was last written
at — neither is justified by what this phase needs yet; this command gives
the audit trail (what was promoted, when, how big) without the harder
point-in-time graph reconstruction.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cartographer import config as config_mod

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    cfg = config_mod.load_config(workspace)
    if cfg.topology.mode != "central":
        console.print("topology is local-only; no promotion history")
        raise typer.Exit(code=0)

    override = config_mod.load_local_override(workspace)
    try:
        from cartographer.indexing.central import get_central_kg
        central_kg = get_central_kg(cfg, override)
    except (ValueError, NotImplementedError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if not central_kg.is_reachable():
        console.print("[red]central KG (Neo4j) is not reachable; check cartographer.local.toml[/red]")
        raise typer.Exit(code=1)

    rows = central_kg.list_promotions(cfg.project.id)
    if not rows:
        console.print("no promotion history yet")
        raise typer.Exit(code=0)

    table = Table()
    table.add_column("Promoted at")
    table.add_column("Commit SHA")
    table.add_column("Nodes", justify="right")
    table.add_column("Edges", justify="right")
    for row in rows:
        table.add_row(
            row.get("promoted_at", ""),
            (row.get("commit_sha") or "")[:12],
            str(row.get("node_count", 0)),
            str(row.get("edge_count", 0)),
        )
    console.print(table)
