# Phase 3: Sync and Lifecycle

## Goal

Handle the data lifecycle gaps that were deferred in Phase 2: deletions, renames, rebase handling, and conflict resolution when local and global indexes diverge. After Phase 3, both the local and global indexes accurately reflect the current state of the codebase — including removed and renamed artifacts — in real time (local, via the watcher) and at promotion time (global, via tombstone detection).

**Entry condition:** Phase 2 is complete and stable. The central topology is in active use on at least one real project. Phase 3 must not start until Phase 2 has been running long enough to surface real-world edge cases in promotion behavior.

---

## Design spike status

**The design spike is complete.** All four protocol documents have been written and are in `docs/phases/phase-3-protocols/`. Implementation may begin after each protocol is reviewed and accepted.

| Protocol | Document | Status |
|---|---|---|
| Tombstone protocol | [tombstone-protocol.md](phase-3-protocols/tombstone-protocol.md) | Draft — awaiting review |
| Rename tracking protocol | [rename-tracking-protocol.md](phase-3-protocols/rename-tracking-protocol.md) | Draft — awaiting review |
| Rebase and force-push policy | [rebase-policy.md](phase-3-protocols/rebase-policy.md) | Draft — awaiting review |
| Conflict resolution policy | [conflict-resolution-policy.md](phase-3-protocols/conflict-resolution-policy.md) | Draft — awaiting review |

---

## References

| Document | What to read |
|---|---|
| [DATA_MODEL.md](../DATA_MODEL.md) | Section 7: known gaps and deferred concerns |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Section 9: what is not in scope (the original deferral rationale) |
| [ROADMAP.md](../ROADMAP.md) | Phase 3 entry condition and design spike requirement |
| [phase-3-protocols/](phase-3-protocols/) | All four protocol documents |

---

## Scope

### Implementation scope

| Concern | What ships | Primary mechanism |
|---|---|---|
| Local deletion cleanup | Deleted files removed from local VDB/KG in real time | `watcher.py` `on_deleted` handler |
| Local rename cleanup | Old path removed from local VDB/KG in real time; new path ingested | `watcher.py` `on_moved` enhanced |
| Global deletion (tombstone) | Deleted artifacts marked in global index at promote time; stale nodes not deleted immediately | `promote.py` index comparison |
| Global rename (supersedes) | Old identity linked to new identity via `supersedes` edge at promote time | `promote.py` git rename detection |
| Stale tombstone cleanup | `cartographer gc` removes tombstoned artifacts older than retention period | New `commands/gc.py` |
| Rebase handling | Policy implementation per `rebase-policy.md` | `promote.py` + operator runbook |
| Conflict resolution | Conflict notice injected into recall context when local and global `updated_at` differ | Recall hooks |

### Explicitly out of scope

- Real-time bidirectional sync (explicitly a non-goal per [ARCHITECTURE.md](../ARCHITECTURE.md))
- Cross-tenant reconciliation (never in scope)
- Standards Registry and web app (independent track)

---

## Component breakdown

### 1. Watcher: local deletion and rename cleanup

**This is the primary mechanism for keeping the local index accurate.** The watcher (`cli/src/cartographer/runtime/watcher.py`) already receives OS-level `deleted` and `moved` events. It currently ignores deleted files and only ingests the destination of a move, leaving stale entries in the local index indefinitely.

**Changes required (`watcher.py`):**

`DirtyTracker` — add deleted path tracking alongside dirty paths:
```python
def mark_deleted(self, project_id: str, path: Path) -> None: ...
def ready_batches(self, debounce: float) -> list[tuple[str, set[Path], set[Path]]]:
    # returns (project_id, dirty_paths, deleted_paths)
```

`_ProjectHandler` — add `on_deleted` and fix `on_moved`:
```python
def on_deleted(self, event: FileSystemEvent) -> None:
    if not event.is_directory:
        self._tracker.mark_deleted(self._project_id, Path(event.src_path))

def on_moved(self, event: FileSystemEvent) -> None:
    if not event.is_directory:
        self._tracker.mark_deleted(self._project_id, Path(event.src_path))
        self._consider(event.dest_path)
```

`_flush_ready` — call VDB/KG delete for each deleted path before ingesting dirty paths:
```python
for project_id, dirty_paths, deleted_paths in tracker.ready_batches(DEBOUNCE_SECONDS):
    for path in deleted_paths:
        vdb.delete_by_path(local_dir / "vdb.lance", str(path))
        kg.delete_by_path(local_dir / "kg.kuzu", str(path))
    ingest_paths(existing_dirty_paths, ...)
```

**New driver operations required:**
- `vdb.delete_by_path(db_path, path)` — delete all chunks for a given path from local scope
- `kg.delete_by_path(kg_path, path)` — detach-delete all nodes for a given path from local scope

**Why this matters:** Without this, a deleted or renamed file continues to surface in local recall context until the next `cartographer seed`. The watcher already has the events; adding these handlers requires minimal new code.

---

### 2. Tombstone protocol (global index, at promote time)

See [tombstone-protocol.md](phase-3-protocols/tombstone-protocol.md) for the full spec.

Summary of changes:
- `vdb.ChunkRecord` — add `is_tombstone: bool = False`
- `vdb.py:_schema()` (LanceDB) — add `is_tombstone` column
- `vdb_pgvector.PgvectorDriver` — add `is_tombstone` column; filter in `query()`
- `promote.py` — index comparison: `global_paths - local_paths` → write tombstones
- Recall hooks — filter `is_tombstone = True` / `tombstoned_at != ""` from query results
- `cartographer gc` — new command; removes tombstones older than retention period

---

### 3. Rename tracking (global index, at promote time)

See [rename-tracking-protocol.md](phase-3-protocols/rename-tracking-protocol.md) for the full spec.

Summary of changes:
- `registry.ProjectRecord` — add `last_promoted_sha: str = ""`
- `promote.py` — git rename detection; write `supersedes` edges; update `last_promoted_sha`
- Recall hooks — follow `supersedes` edges; tag with `origin: renamed`

---

### 4. `cartographer gc`

New CLI command added in Phase 3:

```
cartographer gc [--dry-run] [--older-than <days>]
```

Removes tombstoned artifacts from the global index that have exceeded the retention period (default: 30 days). `--dry-run` reports what would be removed without writing.

---

### 5. Conflict resolution (recall hooks)

See [conflict-resolution-policy.md](phase-3-protocols/conflict-resolution-policy.md) for the full spec.

Summary of changes:
- Recall hooks (`preload.py`, `retrieve.py`, `recall.py`) — add conflict detection at merge step; inject notice into context when local and global `updated_at` differ
- `cartographer.toml` schema — add `conflict_threshold_seconds` and `conflict_notice` to `[retrieval]` section

---

## Open questions

All open questions from the design spike are resolved. See the protocol documents for decisions.

| Question | Resolved in |
|---|---|
| Tombstone schema | `tombstone-protocol.md` — `is_tombstone` in VDB; `tombstoned_at` in KG |
| Rename detection strategy | `rename-tracking-protocol.md` — git diff primary, index comparison fallback |
| Conflict definition | `conflict-resolution-policy.md` — `updated_at` diff at recall time |
| Retention policy default | `tombstone-protocol.md` — 30 days |
| Whether `kg_move_node` requires a new MCP tool | `rename-tracking-protocol.md` — no; `supersedes` is a standard `RelatesTo` edge |
| Local index deletion/rename cleanup mechanism | This document — watcher `on_deleted` / `on_moved` handlers |

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Deleting a file while `cartographer serve` is running removes it from the local index within the debounce window | Delete a file; wait 5s; run `cartographer recall <query that matched it>`; confirm it no longer appears |
| 2 | Renaming a file while `cartographer serve` is running removes the old path from the local index and ingests the new path | Rename a file; wait 5s; query old path → not found; query new path → found |
| 3 | Deleting a file on a branch and promoting does not leave the artifact permanently in the global index — it is tombstoned | Delete a file; promote; check global VDB stats; confirm artifact is tombstoned not absent |
| 4 | Tombstoned artifacts do not appear in recall context (local or global) | Tombstone an artifact; run a recall query that would have matched it; confirm it is absent from results |
| 5 | Renaming a file and promoting links old identity to new identity via `supersedes` edge | Rename a file; promote; query old path in KG; confirm `supersedes` edge to new path exists |
| 6 | `cartographer gc` removes tombstoned artifacts older than the retention period | Tombstone an artifact; set `--older-than 0`; run gc; confirm artifact is deleted from global index |
| 7 | `cartographer gc --dry-run` reports what would be removed without writing | Run dry-run; confirm output matches expected artifacts; confirm global index unchanged |
| 8 | Recall surfaces a conflict notice when local and global `updated_at` differ | Promote an artifact; edit it locally without promoting; run recall; confirm conflict notice appears |
| 9 | Suppressing `conflict_notice = false` in config removes the notice without affecting which version is returned | Set `conflict_notice = false`; run recall on a conflicting artifact; confirm no notice, local version returned |
| 10 | All Phase 2 exit criteria still pass after Phase 3 changes | Re-run Phase 2 acceptance test; confirm no regression |

---

## Test approach

### Protocol review gate

Before any code is written for a given protocol, the protocol document is reviewed and accepted. The review must confirm:
- The protocol handles the stated edge cases
- The protocol does not break the Phase 2 promotion idempotency guarantee
- Any MCP tool contract changes are backward-compatible or have an ADR

### Unit tests

| Area | What to test |
|---|---|
| `DirtyTracker.mark_deleted` | Deleted paths batched and returned separately from dirty paths |
| `_ProjectHandler.on_deleted` | File deletion event marks path as deleted in tracker |
| `_ProjectHandler.on_moved` | Move event marks src as deleted and enqueues dest for ingestion |
| `vdb.delete_by_path` | All chunks for path removed from local VDB |
| `kg.delete_by_path` | All nodes for path detach-deleted from local KG |
| Tombstone record creation | `promote.py` writes `is_tombstone=True` on deleted paths |
| Rename detection | `promote.py` detects renames via git diff; writes `supersedes` edge |
| `gc` retention filter | Only tombstones older than `--older-than` are removed |
| Conflict detection | `updated_at` diff triggers conflict notice in merged recall result |

### Integration tests

Require a real central backend (pgvector + Neo4j) and a git repo with known deletion and rename history:
- Delete a file; promote; verify tombstone in global VDB; verify `cartographer gc` removes it after retention
- Rename a file; promote; verify `supersedes` edge in global KG; verify recall follows redirect
- Edit a file locally after another developer promotes a different version; verify conflict notice in context

### Regression test

Phase 2 end-to-end acceptance test (two-developer walkthrough) must pass unchanged after Phase 3 changes. Required gate before Phase 3 is considered complete.

---

*For the known gaps this phase closes, see [DATA_MODEL.md: Known gaps](../DATA_MODEL.md). For Phase 2 foundation, see [phase-2-central.md](phase-2-central.md).*
