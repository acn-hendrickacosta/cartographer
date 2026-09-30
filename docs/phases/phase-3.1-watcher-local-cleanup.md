# Phase 3.1: Watcher — Local Index Deletion and Rename Cleanup

## Goal

Keep the local VDB and KG accurate in real time when files are deleted or renamed. After Phase 3.1, a developer working in a session where a file was deleted or renamed will no longer see stale entries surfacing in local recall context. No central backend required — this is purely local.

**Entry condition:** Phase 2 code complete. No central backend required for this pass.

---

## References

| Document | What to read |
|---|---|
| [phase-3-protocols/tombstone-protocol.md](phase-3-protocols/tombstone-protocol.md) | Local deletion section |
| [phase-3-protocols/rename-tracking-protocol.md](phase-3-protocols/rename-tracking-protocol.md) | Local rename cleanup section |
| `cli/src/cartographer/runtime/watcher.py` | Current implementation — missing `on_deleted`, incomplete `on_moved` |

---

## Problem

The watcher (`watcher.py`) already receives OS-level `deleted` and `moved` events from watchdog. It currently:

- **Ignores deleted files** — no `on_deleted` handler; `_consider()` checks `p.is_file()` which is `False` for deleted files, so events are silently dropped
- **Partially handles moves** — `on_moved` enqueues `dest_path` (new path) but never removes `src_path` (old path) from the local index

Result: deleted and renamed files accumulate as stale entries in the local VDB/KG indefinitely, surfacing in Claude's recall context until the developer manually runs `cartographer seed`.

---

## Scope

### In scope

| Component | Change |
|---|---|
| `DirtyTracker` | Add `mark_deleted(project_id, path)` and separate deleted-path tracking |
| `_ProjectHandler.on_deleted` | New handler — marks path as deleted in tracker |
| `_ProjectHandler.on_moved` | Enhanced — marks `src_path` as deleted; enqueues `dest_path` for ingestion (existing behaviour) |
| `_flush_ready` | Call `vdb.delete_by_path` / `kg.delete_by_path` for deleted paths before ingesting dirty paths |
| `vdb.delete_by_path(db_path, path)` | New function — deletes all chunks for a given path from local LanceDB |
| `kg.delete_by_path(kg_path, path)` | New function — detach-deletes all nodes for a given path from local Kuzu |

### Explicitly out of scope

- Tombstone records in the global index (Phase 3.2)
- `supersedes` edges or rename history in the KG (Phase 3.3)
- Any change to `promote.py` (Phase 3.2)
- Central backend drivers (not touched)

---

## Component breakdown

### `DirtyTracker`

Add a separate `_deleted` dict alongside `_dirty`. `mark_deleted` works like `mark` but flags the path for removal rather than ingestion. `ready_batches` returns both sets:

```python
def mark_deleted(self, project_id: str, path: Path) -> None:
    with self._lock:
        self._deleted.setdefault(project_id, set()).add(path)
        self._last_touch[project_id] = time.monotonic()

def ready_batches(self, debounce: float) -> list[tuple[str, set[Path], set[Path]]]:
    # returns (project_id, dirty_paths, deleted_paths)
```

### `_ProjectHandler`

```python
def on_deleted(self, event: FileSystemEvent) -> None:
    if not event.is_directory:
        self._tracker.mark_deleted(self._project_id, Path(event.src_path))

def on_moved(self, event: FileSystemEvent) -> None:
    if not event.is_directory:
        self._tracker.mark_deleted(self._project_id, Path(event.src_path))
        self._consider(event.dest_path)
```

### `_flush_ready`

Process deletions before ingesting dirty paths so that a rename (delete + add) doesn't leave a brief window where both old and new paths are in the index:

```python
for project_id, dirty_paths, deleted_paths in tracker.ready_batches(DEBOUNCE_SECONDS):
    record = registry.get_project(project_id)
    if record is None:
        continue
    workspace = Path(record.location)
    local_dir = workspace / ".cartographer" / "local"
    try:
        cfg = config_mod.load_config(workspace)
    except Exception:
        continue

    for path in deleted_paths:
        try:
            vdb.delete_by_path(local_dir / "vdb.lance", str(path))
            kg.delete_by_path(local_dir / "kg.kuzu", str(path))
        except Exception:
            pass  # best-effort; stale entry is a UX issue, not a crash

    existing_dirty = [p for p in dirty_paths if p.exists()]
    if not existing_dirty:
        continue
    # ... existing ingest logic
```

### `vdb.delete_by_path(db_path, path)`

```python
def delete_by_path(db_path: Path, path: str) -> int:
    """Delete all chunks for the given file path from the local VDB. Returns deleted count."""
    if not db_path.exists():
        return 0
    import lancedb
    db = lancedb.connect(str(db_path))
    deleted = 0
    for table_name in (db.list_tables().tables if hasattr(db.list_tables(), "tables") else db.list_tables()):
        try:
            tbl = db.open_table(table_name)
            tbl.delete(f"path = '{path}'")
            deleted += 1
        except Exception:
            pass
    return deleted
```

### `kg.delete_by_path(kg_path, path)`

```python
def delete_by_path(kg_path: Path, path: str) -> int:
    """Detach-delete all Artifact nodes for the given path from the local KG."""
    if not kg_path.exists():
        return 0
    import kuzu
    db = kuzu.Database(str(kg_path))
    conn = kuzu.Connection(db)
    result = conn.execute(
        "MATCH (a:Artifact) WHERE a.path = $path DETACH DELETE a RETURN count(*)",
        {"path": path},
    )
    return result.get_next()[0] if result.has_next() else 0
```

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Deleting a file while `cartographer serve --watch` is running removes it from the local VDB within the debounce window (default 3s) | Delete a file; wait 5s; run `cartographer recall <query that matched it>`; confirm it no longer appears |
| 2 | Deleting a file removes it from the local KG | Delete a file; wait 5s; query the KG for the deleted path; confirm no node exists |
| 3 | Renaming a file removes the old path from local VDB and KG within the debounce window | Rename a file; wait 5s; query old path → not found; query new path → found |
| 4 | Deleting a file that was never indexed does not crash the watcher | Delete an uningestible or untracked file; confirm `cartographer serve` keeps running |
| 5 | Watcher continues watching all other projects after a deletion failure in one project | Simulate a KG delete error on project A; confirm project B's changes still flush |
| 6 | All existing watcher tests still pass | Run `python -m pytest cli/tests/test_watcher.py` |

---

## Test approach

### Unit tests (add to `cli/tests/test_watcher.py`)

- `DirtyTracker.mark_deleted` — deleted paths batch separately from dirty paths
- `_ProjectHandler.on_deleted` — event marks src_path as deleted
- `_ProjectHandler.on_moved` — event marks src_path as deleted AND enqueues dest_path
- `_flush_ready` — calls `delete_by_path` for deleted paths before `ingest_paths`
- `vdb.delete_by_path` — chunks for path are removed; other paths unaffected
- `kg.delete_by_path` — nodes for path are detach-deleted; other nodes unaffected

No central backend required. All tests run against local LanceDB and Kuzu.

---

*Next pass: [Phase 3.2 — Tombstone Protocol](phase-3.2-tombstone.md)*
