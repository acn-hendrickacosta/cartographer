"""`cartographer detect`: dry-run report of existing Claude configuration."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cartographer import claude_merge

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root to inspect"),
) -> None:
    workspace = path.resolve()
    entries = claude_merge.detect(workspace)

    table = Table(title=f"cartographer detect: {workspace}")
    table.add_column("File")
    table.add_column("Exists")
    table.add_column("init would")
    table.add_column("Detail")
    for entry in entries:
        table.add_row(entry.name, "yes" if entry.exists else "no", entry.action, entry.detail)
    console.print(table)
