"""Shared PID-file helpers for `cartographer serve`'s lifecycle.

One `serve` instance covers every registered project on a machine (workspace is
routed per-request), so the PID file lives alongside registry.json under
~/.cartographer/, not per-project. Used by serve.py's own start/stop/status
commands and by doctor.py, so liveness-checking logic lives in exactly one place.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


def pid_file_path() -> Path:
    return Path.home() / ".cartographer" / "serve.pid"


@dataclass
class ServeState:
    pid: int
    vdb_pid: int
    kg_pid: int
    vdb_port: int
    kg_port: int
    started_at: str


def write_pid_file(state: ServeState) -> None:
    path = pid_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def read_pid_file() -> ServeState | None:
    path = pid_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ServeState(**data)
    except Exception:
        return None


def remove_pid_file() -> None:
    try:
        pid_file_path().unlink()
    except FileNotFoundError:
        pass


def is_alive(pid: int) -> bool:
    """True if a process with this PID currently exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else — still alive
    return True


def check_health(port: int, timeout: float = 1.0) -> dict | None:
    """GET /health on a server port. Returns the parsed JSON, or None if unreachable."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def is_healthy(state: ServeState) -> bool:
    """True if both the VDB and KG servers respond on their configured ports."""
    return check_health(state.vdb_port) is not None and check_health(state.kg_port) is not None


def current_running_state() -> ServeState | None:
    """Return the ServeState for a live instance, or None — cleaning up a stale
    PID file automatically if the recorded process no longer exists."""
    state = read_pid_file()
    if state is None:
        return None
    if not is_alive(state.pid):
        remove_pid_file()
        return None
    return state
