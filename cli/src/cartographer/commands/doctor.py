"""`cartographer doctor`: validate config, local index reachability, and MCP wiring."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod
from cartographer.indexing import kg, vdb

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    healthy = True

    if not config_mod.config_exists(workspace):
        console.print("[red]FAIL[/red] cartographer.toml not found; run 'cartographer init'")
        raise typer.Exit(code=1)

    try:
        cfg = config_mod.load_config(workspace)
        console.print("[green]OK[/green]   cartographer.toml parses and validates")
    except Exception as exc:  # noqa: BLE001 - this is the CLI's user-facing report boundary
        console.print(f"[red]FAIL[/red] cartographer.toml invalid: {exc}")
        raise typer.Exit(code=1) from exc

    local_dir = workspace / ".cartographer" / "local"

    if vdb.is_readable(local_dir / "vdb.lance"):
        console.print("[green]OK[/green]   local VDB opens")
    else:
        console.print("[red]FAIL[/red] local VDB not readable")
        healthy = False

    if kg.is_readable(local_dir / "kg.kuzu"):
        console.print("[green]OK[/green]   local KG opens")
    else:
        console.print("[red]FAIL[/red] local KG not readable")
        healthy = False

    if cfg.topology.mode == "central":
        console.print("[yellow]INFO[/yellow] central backend driver not yet implemented (Phase 2)")

    mcp_path = workspace / ".mcp.json"
    mcp_wired = False
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            mcp_wired = "cartographer" in data.get("mcpServers", {})
        except json.JSONDecodeError:
            pass

    if mcp_wired:
        console.print("[green]OK[/green]   Cartographer MCP entries present in .mcp.json")
    else:
        console.print("[yellow]INFO[/yellow] Cartographer MCP entries not found; run 'cartographer init'")

    if not healthy:
        raise typer.Exit(code=1)
    console.print("[bold green]doctor: all local checks passed[/bold green]")
