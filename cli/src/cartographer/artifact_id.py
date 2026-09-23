"""Stable identity helpers.

Per PROJECT_BRIEF.md Section 4 and 7.4: artifact identity is a stable key derived
from file path plus symbol, or a spec id -- never a commit SHA. This is what makes
promotion an idempotent upsert instead of history-dependent.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def artifact_id(path: str, symbol: str | None = None, *, spec_id: str | None = None) -> str:
    """Build a stable artifact identity for a KG node or VDB chunk.

    Uses `spec_id` directly when given (specs are identified by their own id).
    Otherwise combines `path` and `symbol` (symbol may be None for whole-file nodes).
    """
    if spec_id:
        return f"spec:{spec_id}"
    key = path if symbol is None else f"{path}::{symbol}"
    return f"path:{key}"


def chunk_id(path: str, ordinal: int, symbol: str | None = None, *, spec_id: str | None = None) -> str:
    """Artifact identity plus a chunk ordinal, for VDB chunk records (Section 7.1)."""
    return f"{artifact_id(path, symbol, spec_id=spec_id)}#{ordinal}"


def _git_remote_url(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def compute_project_id(repo_path: Path) -> str:
    """Deterministic project id: hash of the git remote URL if present, else of the
    resolved absolute repo path.

    Preferring the remote URL means clones on different machines/paths agree on the
    same project id; falling back to the path keeps `init` usable before a remote exists.
    """
    resolved = repo_path.resolve()
    remote = _git_remote_url(resolved)
    basis = remote if remote else str(resolved)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"proj_{digest}"
