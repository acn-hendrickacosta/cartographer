# Phase 3.4: Conflict Resolution — Surface Divergence in Recall Context

**Status:** Code complete as of 2026-10-05. All exit criteria verified except #8 (Phase 2's two-developer walkthrough, a standing manual exercise deferred since Phase 2 itself — not newly closeable by this phase). 195 unit tests passing (17 new) plus 30 integration tests against a live pgvector+Neo4j backend, including a full two-developer conflict-then-resolve scenario. The conflict-detection design in this doc's original draft relied on incidental top-k similarity overlap to find a local hit's global counterpart — corrected during implementation to an explicit per-path lookup; see the note under "Conflict detection at merge step" below.

All four Phase 3 sub-phases (3.1, 3.1.1, 3.1.2, 3.2, 3.2.1, 3.3, 3.4) are now code-complete. Per ROADMAP.md, Phase 3 as a whole still awaits the Phase 2 two-developer walkthrough before it can be marked closed.

## Goal

When a developer's local version of an artifact diverges from the version in the global index (a different developer promoted a different version), a conflict notice is injected into Claude's recall context. Claude is informed of the divergence and attributes its answer to the local version explicitly. The developer is not blocked — local always wins for reads.

**Entry condition:** Phase 3.3 complete. Phase 3.4 has no hard dependency on 3.3 (it is a pure read-path addition), but the global index should be accurate (tombstones working, renames tracked) before conflict detection is useful in practice.

---

## References

| Document | What to read |
|---|---|
| [phase-3-protocols/conflict-resolution-policy.md](phase-3-protocols/conflict-resolution-policy.md) | Full conflict resolution spec |
| `cli/src/cartographer/runtime/scripts/user_prompt_submit.py` | Current merge step — add conflict detection here |
| `cli/src/cartographer/runtime/scripts/session_start.py` | Same merge step — add conflict detection here |
| `cli/src/cartographer/commands/recall.py` | Same merge step — add conflict detection here |

---

## Scope

### In scope

| Component | Change |
|---|---|
| `user_prompt_submit.py` | Add conflict detection at merge step; prepend notice to conflicting result |
| `session_start.py` | Same |
| `recall.py` | Same |
| `config.py` — `RetrievalSection` | Add `conflict_threshold_seconds: int = 0` and `conflict_notice: bool = True` |
| `cartographer.example.toml` | Document new `[retrieval]` fields |

### Explicitly out of scope

- Merging local and global content (developer responsibility via git)
- Asking Claude to choose between versions (Claude is informed only)
- Any write to the index at conflict time (detection is in-memory only, no schema changes)
- Cross-tenant conflict detection (never in scope)

---

## Component breakdown

### Config additions

```python
class RetrievalSection(BaseModel):
    top_k: int = 8
    per_turn_tokens: int = 1000
    preload_tokens: int = 2000
    conflict_threshold_seconds: int = 0   # 0 = any updated_at difference counts as conflict
    conflict_notice: bool = True           # set False to suppress notices
```

### Conflict detection at merge step

**Corrected during implementation (2026-10-05), before this phase was built —
see the note below the original sketch.**

The original sketch below built `global_by_path` from `global_hits` — the
top-k *vector similarity* results for the current query. That is wrong: a
local hit's same-path global counterpart only appears in `global_hits` if it
*also* happens to rank in the top-k semantic matches for this specific query.
That holds for a trivial local edit (embedding barely moves) but silently
fails to detect a conflict for exactly the case this feature exists for — a
local version that has diverged significantly from the promoted one, whose
embedding has therefore also diverged enough to drop out of the top-k
entirely. The exit-criteria test as originally written (a small, deliberate
local edit) would not have caught this, since a small edit is exactly the
case where incidental top-k overlap still holds.

**Original sketch (do not implement this way):**

```python
def _detect_conflict(local_hit: dict, global_hit: dict, threshold_seconds: int) -> bool:
    local_ts = local_hit.get("updated_at", "")
    global_ts = global_hit.get("updated_at", "")
    if not local_ts or not global_ts or local_ts == global_ts:
        return False
    if threshold_seconds == 0:
        return True
    try:
        from datetime import datetime, timezone
        local_dt = datetime.fromisoformat(local_ts).replace(tzinfo=timezone.utc)
        global_dt = datetime.fromisoformat(global_ts).replace(tzinfo=timezone.utc)
        return abs((local_dt - global_dt).total_seconds()) > threshold_seconds
    except Exception:
        return False


# WRONG: global_hits is a top-k similarity result, not a path index — a
# diverged local hit's counterpart may simply not be in this list at all.
global_by_path = {h.get("path"): h for h in global_hits}

conflict_notices: list[str] = []
for hit in local_hits:
    path = hit.get("path")
    global_hit = global_by_path.get(path)
    if global_hit and _detect_conflict(hit, global_hit, cfg.retrieval.conflict_threshold_seconds):
        ...
```

**Corrected approach:** for each local hit, look the same path up directly in
the global index via `PgvectorDriver.query_by_path(project_id, path)` — the
exact-path lookup Phase 3.3 already built for rename redirects — instead of
relying on incidental top-k overlap. This guarantees the comparison happens
regardless of how far the content has drifted, and reuses existing
infrastructure rather than adding new surface area. Lives in a new shared
module, `cartographer/conflict.py`, since the same logic is needed in three
call sites (`recall.py`, `session_start.py`, `user_prompt_submit.py`):

```python
# cartographer/conflict.py
from datetime import datetime

def _is_conflict(local_ts: str, global_ts: str, threshold_seconds: int) -> bool:
    if not local_ts or not global_ts or local_ts == global_ts:
        return False
    if threshold_seconds == 0:
        return True
    try:
        local_dt = datetime.fromisoformat(local_ts)
        global_dt = datetime.fromisoformat(global_ts)
        return abs((local_dt - global_dt).total_seconds()) > threshold_seconds
    except Exception:
        return False


def _notice(path: str, local_ts: str, global_ts: str) -> str:
    return (
        f"⚠ CONFLICT: {path}\n"
        f"  Local:  updated {local_ts} (your working copy)\n"
        f"  Global: updated {global_ts} (last promoted by another developer)\n"
        f"  Showing local. Run 'cartographer promote' after merging to resolve."
    )


def detect_conflicts(local_hits, central_vdb, project_id: str, threshold_seconds: int) -> list[str]:
    """central_vdb may be None (local topology, or central unreachable) — returns []."""
    if central_vdb is None:
        return []
    notices = []
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
        local_ts, global_ts = hit.get("updated_at", ""), global_hit.get("updated_at", "")
        if _is_conflict(local_ts, global_ts, threshold_seconds):
            notices.append(_notice(path, local_ts or "unknown", global_ts or "unknown"))
    return notices
```

Each call site retains a handle to the constructed `central_vdb` driver
(`None` when topology is local or the central backend is unreachable) and
passes it to `detect_conflicts` alongside `local_hits` — no change to how
`global_hits` (the similarity results actually shown to the user) are
computed; this only affects conflict *detection*, which is a separate,
additional lookup.

### Output format

Conflict notices are prepended to the context block, before any artifact content:

```
--- Cartographer recall context ---

⚠ CONFLICT: src/auth/login.py
  Local:  updated 2026-09-29T14:23:00Z (your working copy)
  Global: updated 2026-09-29T09:11:00Z (last promoted by another developer)
  Showing local. Run 'cartographer promote' after merging to resolve.

[code|local] src/auth/login.py
... local content ...

--- end recall context ---
```

If `conflict_notice = false` in config, the `⚠ CONFLICT` block is suppressed entirely. The local version is still returned.

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Recall surfaces a conflict notice when local and global `updated_at` differ | Promote an artifact; edit it locally without promoting; run `cartographer recall`; confirm `⚠ CONFLICT` notice appears before the artifact content |
| 2 | The local version is returned when a conflict is detected (local always wins) | Inspect recall output; confirm local content is shown, not global |
| 3 | No conflict notice appears when local and global `updated_at` are identical | Re-seed without editing; confirm no notice |
| 4 | `conflict_notice = false` in config suppresses the notice without affecting which version is returned | Set `conflict_notice = false`; run recall; confirm no notice; confirm local content returned |
| 5 | `conflict_threshold_seconds = 60` suppresses notices for artifacts within 60 seconds of global | Promote; make a trivial re-index within 60s; run recall; confirm no notice |
| 6 | Conflict detection does not fire in local-only topology (no global hits to compare against) | Run against a local-topology project; confirm no notices |
| 7 | All Phase 3.1–3.3 exit criteria still pass | Run all prior phase tests |
| 8 | Phase 2 acceptance test (two-developer walkthrough) still passes | Re-run walkthrough; confirm no regression |

---

## Test approach

### Unit tests

- `_detect_conflict` returns `True` when `updated_at` differs and threshold is 0
- `_detect_conflict` returns `False` when `updated_at` is identical
- `_detect_conflict` returns `False` when either timestamp is absent
- `_detect_conflict` respects `conflict_threshold_seconds` — no conflict below threshold, conflict above
- Recall output: conflict notice appears before artifact content when conflict detected
- Recall output: no notice when `conflict_notice = false`
- Recall output: no notice in local-only topology (global hits list is empty)

### Integration tests (require pgvector + Neo4j)

- Developer A promotes a file; Developer B edits the same file locally without promoting; Developer B runs `cartographer recall`; confirm `⚠ CONFLICT` in context
- Developer B promotes after merging; run recall again; confirm no conflict notice (both `updated_at` now match)

---

## Phase 3 complete

After Phase 3.4:

1. **Local index** is accurate in real time — deletions and renames cleaned up by the watcher (Phase 3.1)
2. **Global index** correctly reflects the main branch — tombstones for deletions (Phase 3.2), `supersedes` edges for renames (Phase 3.3)
3. **Recall context** surfaces divergence — conflict notices inform Claude and the developer when local and global versions differ (Phase 3.4)

Run the full Phase 3 regression gate before closing:

```bash
python -m pytest cli/tests/test_watcher.py cli/tests/test_recall_global.py cli/tests/test_central_drivers.py -v
```

And re-run the Phase 2 two-developer walkthrough (`docs/runbooks/two-developer-walkthrough.md`) to confirm no regression.

---

*Previous pass: [Phase 3.3 — Rename Tracking](phase-3.3-rename-tracking.md)*
