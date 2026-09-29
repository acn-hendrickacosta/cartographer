"""Shared helpers for Claude Code hook entry points."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_workspace() -> Path:
    """Resolve the project workspace for a hook invocation.

    Claude Code sets CLAUDE_PROJECT_DIR for every hook call — that's the
    authoritative source. CARTO_WORKSPACE is a manual/testing override that
    takes priority when set explicitly (e.g. running a hook script by hand
    outside a real Claude Code session).
    """
    ws = os.environ.get("CARTO_WORKSPACE") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    return Path(ws).resolve()
