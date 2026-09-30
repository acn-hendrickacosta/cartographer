# Conflict Resolution Policy

**Status:** Draft — awaiting review  
**Phase:** 3  
**Blocks:** conflict tagging in recall hooks; conflict surfacing in Claude context

---

## Problem

When two developers work on the same artifact concurrently — Developer A promotes version X, Developer B edits the same file locally and hasn't promoted yet — Developer B's local version shadows the global version during recall (correct behavior). But Developer B has no visibility into the fact that a different version exists in the global index. Claude answers based on B's local version without knowing A's promoted version exists or differs.

A more acute case: Developer B promotes a version, then Developer A promotes a different version of the same file. The global index is now at A's version, but Developer B's local index is at B's version. Neither developer knows about the other's change.

---

## Definition of a conflict

A conflict exists when, at recall time, **all** of the following are true:

1. The artifact has a local version (present in local VDB/KG)
2. The artifact has a global version (present in global VDB/KG)
3. The local `updated_at` and the global `updated_at` differ by more than a configurable threshold (default: 0 — any difference counts)

This is a conservative definition: it flags any case where local and global versions of the same artifact have different timestamps. False positives are possible (e.g., local was re-seeded but content is identical), but they are safe — Claude is only informed, not blocked.

**What is NOT a conflict:**
- Local is newer than global, global hasn't been updated since last promote: normal working state
- Local and global have the same `updated_at`: idempotent re-seed, not a conflict

---

## Resolution rule

**Local always wins for reads.** The existing Phase 2 behavior is preserved: local results shadow global results for the same artifact identity. This is the correct default because:

- Developer B's local version reflects their current working state
- B hasn't merged yet; their local version is the one relevant to their session
- Forcing developers to resolve conflicts before they can read their own code is unacceptable friction

**Merge is out of scope.** Cartographer does not merge content between local and global versions. That is a developer responsibility via standard git workflow.

---

## Conflict surfacing

When a conflict is detected at recall time, the recall context includes a conflict notice **before** the artifact content:

```
⚠ CONFLICT: src/auth/login.py
  Local version:  updated 2026-01-15T14:23:00Z (your working copy)
  Global version: updated 2026-01-15T09:11:00Z (last promoted by another developer)
  Showing local. Run 'cartographer promote' after merging to resolve.
```

**Claude is informed, not asked to resolve.** The notice gives Claude enough context to:
- Know that a divergence exists
- Attribute answers to the local version explicitly
- Suggest that the developer check git for the other version

Claude must not attempt to merge the two versions or choose between them. That decision belongs to the developer.

---

## Detection implementation

At recall merge time (after querying both local and global scopes):

```python
for artifact_id in results_by_id:
    local_result = local_results.get(artifact_id)
    global_result = global_results.get(artifact_id)
    if local_result and global_result:
        if local_result["updated_at"] != global_result["updated_at"]:
            tag conflict on the result
    # local shadows global regardless
    final_results[artifact_id] = local_result or global_result
```

Conflicts are detected and tagged in memory during recall — no new index writes, no schema changes required.

---

## Configuration

```toml
[retrieval]
conflict_threshold_seconds = 0   # 0 = any difference is a conflict
conflict_notice = true            # set to false to suppress notices (not recommended)
```

---

## Data model changes required

| Component | Change |
|---|---|
| Recall hooks (`preload.py`, `retrieve.py`) | Add conflict detection at merge step; inject notice into context |
| `cartographer.toml` schema | Add `conflict_threshold_seconds` and `conflict_notice` to `[retrieval]` section |
| VDB / KG schema | No change — uses existing `updated_at` field |

---

## Open questions resolved

| Question | Decision |
|---|---|
| Definition of conflict | Local and global `updated_at` differ (configurable threshold) |
| Resolution winner | Local always wins (existing Phase 2 behavior) |
| Merge | Out of scope — developer responsibility via git |
| Claude's role | Informed only; must not attempt to merge or choose |
| Schema changes | None — conflict detection is in-memory at recall time |
| False positives | Acceptable — conservative definition; Claude is only informed |

---

## Exit criteria (from phase spec)

| # | Criterion |
|---|---|
| — | Recall surfaces a conflict notice when local and global versions of the same artifact differ |
| — | Claude answers using the local version and explicitly attributes it as such |
| — | Suppressing `conflict_notice = false` in config removes the notice without affecting which version is shown |
