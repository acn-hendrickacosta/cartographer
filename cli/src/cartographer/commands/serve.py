"""`cartographer serve`: start, stop, and check Cartographer's long-running MCP servers.

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

Process lifecycle (PID file, signal handling, child supervision, stop/status) is
Phase 3.2.1 — see docs/phases/phase-3.2.1-serve-process-lifecycle.md.
"""

from __future__ import annotations

import datetime
import os
import shutil
import signal
import subprocess
import threading
import time
from typing import Callable

import typer
from rich.console import Console

from cartographer.runtime import serve_state

console = Console()

VDB_DEFAULT_PORT = 4010
KG_DEFAULT_PORT = 4011

RESTART_BACKOFF_SECONDS = 2.0
CRASH_LOOP_WINDOW_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 10.0

app = typer.Typer(help="Run, stop, or check Cartographer's long-running MCP servers.", invoke_without_command=True)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def supervise(
    procs: list[subprocess.Popen],
    role_names: list[str],
    restart_fns: list[Callable[[], subprocess.Popen]],
    stop_event: threading.Event,
    on_restart: Callable[[list[subprocess.Popen]], None],
    console: Console,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    restart_backoff: float = RESTART_BACKOFF_SECONDS,
    crash_loop_window: float = CRASH_LOOP_WINDOW_SECONDS,
) -> bool:
    """Poll `procs` until `stop_event` is set or a child crash-loops.

    On an unexpected child exit, restart it once after `restart_backoff`. If that
    same child exits again within `crash_loop_window` of the restart, treat it as
    a crash loop and return True (caller should shut everything down and exit
    non-zero) instead of retrying forever. Returns False on a clean, requested stop.
    """
    last_restart: dict[int, float] = {}
    while not stop_event.is_set():
        for idx, p in enumerate(procs):
            ret = p.poll()
            if ret is None:
                continue
            role = role_names[idx]
            console.print(f"[red]{role} exited unexpectedly (code {ret})[/red]")
            now = time.monotonic()
            prev = last_restart.get(idx)
            if prev is not None and (now - prev) < crash_loop_window:
                console.print(
                    f"[red]{role} crash-looped within {crash_loop_window:.0f}s of its last restart; giving up[/red]"
                )
                return True
            console.print(f"[yellow]restarting {role} in {restart_backoff:.0f}s...[/yellow]")
            if stop_event.wait(restart_backoff):
                return False
            last_restart[idx] = time.monotonic()
            procs[idx] = restart_fns[idx]()
            on_restart(procs)
        if stop_event.wait(poll_interval):
            return False
    return False


def _shutdown(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    serve_state.remove_pid_file()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    vdb_port: int = typer.Option(VDB_DEFAULT_PORT, "--vdb-port", help="Port for VDB server"),
    kg_port: int = typer.Option(KG_DEFAULT_PORT, "--kg-port", help="Port for KG server"),
    watch: bool = typer.Option(
        True, "--watch/--no-watch",
        help="Also watch every registered project's files and re-ingest changes automatically. "
             "Runs independently of Claude Code hooks, so it works even where enterprise policy "
             "(e.g. allowManagedHooksOnly) blocks project-defined hooks.",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    existing = serve_state.read_pid_file()
    if existing is not None:
        if serve_state.is_alive(existing.pid) and serve_state.is_healthy(existing):
            console.print(
                f"[red]cartographer serve is already running (pid {existing.pid}, started {existing.started_at})[/red]"
            )
            console.print("Run 'cartographer serve stop' first, or 'cartographer serve status' to inspect it.")
            raise typer.Exit(code=1)
        # stale PID file — process dead or unhealthy; clean up and proceed
        serve_state.remove_pid_file()

    vdb_cmd = shutil.which("cartographer-vdb-server") or "cartographer-vdb-server"
    kg_cmd = shutil.which("cartographer-kg-server") or "cartographer-kg-server"

    def _spawn_vdb() -> subprocess.Popen:
        return subprocess.Popen([vdb_cmd, "--http", "--port", str(vdb_port)])

    def _spawn_kg() -> subprocess.Popen:
        args = [kg_cmd, "--http", "--port", str(kg_port)]
        if watch:
            args.append("--watch")
        return subprocess.Popen(args)

    procs = [_spawn_vdb(), _spawn_kg()]
    started_at = _now()

    def _persist_state() -> None:
        serve_state.write_pid_file(serve_state.ServeState(
            pid=os.getpid(), vdb_pid=procs[0].pid, kg_pid=procs[1].pid,
            vdb_port=vdb_port, kg_port=kg_port, started_at=started_at,
        ))

    _persist_state()

    console.print("[bold green]Cartographer MCP servers running[/bold green]")
    console.print(f"  VDB: [cyan]http://localhost:{vdb_port}/mcp?workspace=<path>[/cyan]")
    console.print(f"  KG:  [cyan]http://localhost:{kg_port}/mcp?workspace=<path>[/cyan]")
    console.print("  Workspace is routed per-request — one server covers all projects.")
    if watch:
        console.print("  Watching all registered projects for changes and re-ingesting automatically.")
    console.print("Press [bold]Ctrl+C[/bold] to stop")

    stop_event = threading.Event()

    def _handle_signal(signum, frame) -> None:  # noqa: ARG001
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        crash_looped = supervise(
            procs,
            role_names=["vdb-server", "kg-server"],
            restart_fns=[_spawn_vdb, _spawn_kg],
            stop_event=stop_event,
            on_restart=lambda _procs: _persist_state(),
            console=console,
        )
    finally:
        console.print("\nShutting down...")
        _shutdown(procs)

    if crash_looped:
        raise typer.Exit(code=1)


@app.command("stop")
def stop() -> None:
    """Stop a running `cartographer serve` instance."""
    state = serve_state.current_running_state()
    if state is None:
        console.print("cartographer serve is not running")
        raise typer.Exit(code=0)

    console.print(f"Stopping cartographer serve (pid {state.pid})...")
    try:
        os.kill(state.pid, signal.SIGTERM)
    except ProcessLookupError:
        serve_state.remove_pid_file()
        console.print("cartographer serve is not running")
        raise typer.Exit(code=0)

    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if serve_state.read_pid_file() is None:
            console.print("[green]stopped[/green]")
            raise typer.Exit(code=0)
        time.sleep(0.2)

    console.print("[yellow]did not stop cleanly within timeout; force-killing[/yellow]")
    for pid in (state.pid, state.vdb_pid, state.kg_pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    serve_state.remove_pid_file()
    console.print("[green]stopped[/green]")


@app.command("status")
def status() -> None:
    """Show whether `cartographer serve` is running and healthy."""
    state = serve_state.current_running_state()
    if state is None:
        console.print("cartographer serve is [yellow]not running[/yellow]")
        raise typer.Exit(code=0)

    vdb_health = serve_state.check_health(state.vdb_port)
    kg_health = serve_state.check_health(state.kg_port)
    watching = bool((kg_health or {}).get("watch"))

    console.print(f"cartographer serve is [green]running[/green] (pid {state.pid}, started {state.started_at})")
    vdb_status = "[green]reachable[/green]" if vdb_health else "[red]unreachable[/red]"
    kg_status = "[green]reachable[/green]" if kg_health else "[red]unreachable[/red]"
    console.print(f"  VDB: port {state.vdb_port}, pid {state.vdb_pid}, {vdb_status}")
    console.print(f"  KG:  port {state.kg_port}, pid {state.kg_pid}, {kg_status} ({'watching' if watching else 'not watching'})")
