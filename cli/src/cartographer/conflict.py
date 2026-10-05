"""Phase 3.4: conflict detection — local vs. global artifact divergence.

Shared by recall.py, session_start.py, and user_prompt_submit.py so the same
detection and notice-formatting logic runs in all three recall paths.

Looks the same path up directly in the global index (PgvectorDriver.query_by_path,
the exact-path lookup Phase 3.3 built for rename redirects) rather than relying
on incidental overlap with the top-k vector-similarity results already being
shown — a local hit whose content has diverged far enough to matter is exactly
the case where its global counterpart's embedding may no longer rank in that
top-k list at all. See docs/phases/phase-3.4-conflict-resolution.md.
"""

from __future__ import annotations

from datetime import datetime


def _is_conflict(local_ts: str, global_ts: str, threshold_seconds: int) -> bool:
    if not local_ts or not global_ts or local_ts == global_ts:
        return False
    try:
        local_dt = datetime.fromisoformat(local_ts)
        global_dt = datetime.fromisoformat(global_ts)
    except Exception:
        return False
    if threshold_seconds == 0:
        return True
    return abs((local_dt - global_dt).total_seconds()) > threshold_seconds


def _notice(path: str, local_ts: str, global_ts: str) -> str:
    return (
        f"⚠ CONFLICT: {path}\n"
        f"  Local:  updated {local_ts} (your working copy)\n"
        f"  Global: updated {global_ts} (last promoted by another developer)\n"
        f"  Showing local. Run 'cartographer promote' after merging to resolve."
    )


def detect_conflicts(
    local_hits: list[dict],
    central_vdb,
    project_id: str,
    threshold_seconds: int,
) -> list[str]:
    """Return a conflict notice for each local hit whose path exists globally
    with a different updated_at. central_vdb may be None (local topology, or
    central unreachable) — returns [] in that case. Never raises: a failed
    per-path lookup is skipped, not fatal, consistent with conflict detection
    being purely informational and never blocking a read."""
    if central_vdb is None:
        return []
    notices: list[str] = []
    for hit in local_hits:
        path = hit.get("path")
        if not path:
            continue
        try:
            global_hit = central_vdb.query_by_path(project_id, path)
        except Exception:
            continue
        if not global_hit:
            continue
        local_ts = hit.get("updated_at", "")
        global_ts = global_hit.get("updated_at", "")
        if _is_conflict(local_ts, global_ts, threshold_seconds):
            notices.append(_notice(path, local_ts or "unknown", global_ts or "unknown"))
    return notices
