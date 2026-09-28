"""`cartographer ui`: start the local knowledge browser.

Launches a FastAPI + uvicorn server on localhost:7341 and opens the browser.
Requires `cartographer-cli[ui]` extras (fastapi, uvicorn).
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod

console = Console()
PORT = 7341
HOST = "127.0.0.1"


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
    port: int = typer.Option(PORT, "--port", help="Port to listen on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Skip opening the browser"),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    try:
        import uvicorn  # type: ignore[import]
    except ImportError:
        console.print(
            "[red]uvicorn is required for 'cartographer ui'. "
            "Install with: pip install \"cartographer-cli[ui]\"[/red]"
        )
        raise typer.Exit(code=1)

    try:
        from cartographer.ui.server import build_app
    except ImportError as exc:
        console.print(f"[red]FastAPI not available: {exc}[/red]")
        raise typer.Exit(code=1)

    app = build_app(workspace)
    url = f"http://{HOST}:{port}"
    console.print(f"[bold]cartographer ui[/bold] → {url}")
    console.print("  Press Ctrl+C to stop.")

    if not no_browser:
        # Open after a short delay so the server is up
        import threading
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=HOST, port=port, log_level="warning")
