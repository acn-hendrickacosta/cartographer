"""`cartographer taxonomy`: inspect the canonical edge-type taxonomy.

Phase 4 governance: at org scale, schema drift across projects (a typo'd or
inconsistent edge type) makes cross-project Cypher unreliable. This command
is read-only — enforcement happens at `cartographer seed` time (lint step,
`--strict` flag) and `cartographer doctor` (version pin check).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from cartographer.taxonomy import CANONICAL_EDGE_TYPES, CANONICAL_TAXONOMY_VERSION, EDGE_TYPE_DEFINITIONS

console = Console()

app = typer.Typer(help="Inspect the canonical edge-type taxonomy.")


@app.command("list")
def list_taxonomy() -> None:
    """Print the canonical edge types and their definitions."""
    console.print(f"[bold]Canonical edge taxonomy[/bold] (version {CANONICAL_TAXONOMY_VERSION})")
    table = Table()
    table.add_column("Edge type")
    table.add_column("Source")
    table.add_column("Definition")
    for edge_type in sorted(CANONICAL_EDGE_TYPES):
        source, definition = EDGE_TYPE_DEFINITIONS.get(edge_type, ("?", ""))
        table.add_row(edge_type, source, definition)
    console.print(table)
