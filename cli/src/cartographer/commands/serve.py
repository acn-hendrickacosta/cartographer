"""`cartographer serve`: start MCP servers in HTTP mode for enterprise environments.

Enterprise policy often blocks stdio MCP servers. This command runs both MCP servers
as long-running HTTP servers on localhost. A single instance handles all projects —
the workspace is passed per-request via query parameter in the URL:

    http://localhost:4010/mcp?workspace=/path/to/project

Each project's .mcp.json (written by `cartographer init`) bakes in its own workspace
path, so Claude Code routes requests to the right index automatically.

The background filesystem watcher (--watch) runs inside the KG server subprocess,
not here (Phase 3.1.1). Kuzu allows only one process to hold a KG's write lock at a
time, so the watcher and the KG MCP tools must share a process to avoid fighting
over that lock; `cartographer seed` delegates to that same subprocess via its
POST /api/ingest route when it detects this command is running. See
docs/phases/phase-3.1.1-management-server.md.
"""

from __future__ import annotations

import shutil
import subprocess

import typer
from rich.console import Console

console = Console()

VDB_DEFAULT_PORT = 4010
KG_DEFAULT_PORT = 4011


def run(
    vdb_port: int = typer.Option(VDB_DEFAULT_PORT, "--vdb-port", help="Port for VDB server"),
    kg_port: int = typer.Option(KG_DEFAULT_PORT, "--kg-port", help="Port for KG server"),
    watch: bool = typer.Option(
        True, "--watch/--no-watch",
        help="Also watch every registered project's files and re-ingest changes automatically. "
             "Runs independently of Claude Code hooks, so it works even where enterprise policy "
             "(e.g. allowManagedHooksOnly) blocks project-defined hooks.",
    ),
) -> None:
    vdb_cmd = shutil.which("cartographer-vdb-server") or "cartographer-vdb-server"
    kg_cmd = shutil.which("cartographer-kg-server") or "cartographer-kg-server"

    kg_args = [kg_cmd, "--http", "--port", str(kg_port)]
    if watch:
        kg_args.append("--watch")

    procs = [
        subprocess.Popen([vdb_cmd, "--http", "--port", str(vdb_port)]),
        subprocess.Popen(kg_args),
    ]

    console.print("[bold green]Cartographer MCP servers running[/bold green]")
    console.print(f"  VDB: [cyan]http://localhost:{vdb_port}/mcp?workspace=<path>[/cyan]")
    console.print(f"  KG:  [cyan]http://localhost:{kg_port}/mcp?workspace=<path>[/cyan]")
    console.print("  Workspace is routed per-request — one server covers all projects.")
    if watch:
        console.print("  Watching all registered projects for changes and re-ingesting automatically.")
    console.print("Press [bold]Ctrl+C[/bold] to stop")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        console.print("\nShutting down...")
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
