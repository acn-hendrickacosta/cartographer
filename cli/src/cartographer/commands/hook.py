"""`cartographer hook <name>`: entry points for the four Claude Code hooks.

Claude Code invokes these as shell commands from `.claude/settings.json`.
Because `cartographer` is on PATH after pip install, no absolute paths are
needed in the settings file — the hooks config simply says:
  "command": "cartographer hook enqueue"
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="hook",
    help="Claude Code hook runners (invoked automatically by Claude Code).",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("enqueue")
def enqueue() -> None:
    """PostToolUse: mark changed file dirty in the queue."""
    from cartographer.runtime.scripts.post_tool_use import main
    main()


@app.command("flush")
def flush() -> None:
    """Stop: embed and index all queued files."""
    from cartographer.runtime.scripts.on_stop import main
    main()


@app.command("preload")
def preload() -> None:
    """SessionStart: inject top-k artifacts into session context."""
    from cartographer.runtime.scripts.session_start import main
    main()


@app.command("retrieve")
def retrieve() -> None:
    """UserPromptSubmit: inject per-turn retrieval context."""
    from cartographer.runtime.scripts.user_prompt_submit import main
    main()
