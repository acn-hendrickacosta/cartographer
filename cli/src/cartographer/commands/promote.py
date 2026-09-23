"""`cartographer promote`: manual promotion of merged artifacts to the global index.

Central backend drivers are Phase 2 work (PROJECT_BRIEF.md Section 11) and are not
implemented in this CLI. This command reports that plainly rather than pretending to
promote something it cannot.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

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
    if cfg.topology.mode == "local":
        console.print("topology is local-only; nothing to promote")
        raise typer.Exit(code=0)

    console.print(
        "[yellow]central backend driver not yet implemented (Phase 2)[/yellow]: "
        "promotion needs a configured central VDB/KG backend, which this CLI version "
        "does not provide yet. See PROJECT_BRIEF.md Section 11."
    )
    raise typer.Exit(code=1)
