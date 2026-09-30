# Phase 3.2: Tombstone Protocol — Global Index Deletion at Promote Time

## Goal

When a file is deleted and the branch is promoted, the artifact is marked as tombstoned in the global index rather than left as a permanently stale entry. Tombstoned artifacts are excluded from recall context. A `cartographer gc` command cleans up tombstones after a configurable retention period.

**Entry condition:** Phase 3.1 complete. A provisioned central backend (pgvector + Neo4j) is required for integration testing.

---

## References

| Document | What to read |
|---|---|
| [phase-3-protocols/tombstone-protocol.md](phase-3-protocols/tombstone-protocol.md) | Full tombstone spec |
| `cli/src/cartographer/commands/promote.py` | Current promote — no tombstone detection |
| `cli/src/cartographer/indexing/vdb.py` | `ChunkRecord`, `_schema()` — need `is_tombstone` |
| `cli/src/cartographer/indexing/vdb_pgvector.py` | Central VDB driver — need `is_tombstone` column |

---

## Scope

### In scope

| Component | Change |
|---|---|
| `vdb.ChunkRecord` | Add `is_tombstone: bool = False` |
| `vdb.py:_schema()` | Add `is_tombstone` column to LanceDB Arrow schema |
| `vdb_pgvector.PgvectorDriver` | Add `is_tombstone` column; filter in `query()`, `ensure_collection()`, `upsert()` |
| `kg.Node` attrs | Document `tombstoned_at` as a reserved key (string, ISO timestamp, empty = not tombstoned) |
| `promote.py` | Add index comparison deletion detection; write tombstone records |
| `vdb_server.py` / `kg_server.py` | Filter tombstoned results from all query responses |
| Recall hooks (`preload.py`, `user_prompt_submit.py`, `recall.py`) | Add tombstone filter to global VDB/KG queries |
| `commands/gc.py` | New command |
| `cli/tests/test_recall_global.py` | Add tombstone filter regression tests |

### Explicitly out of scope

- Rename detection or `supersedes` edges (Phase 3.3)
- Local index tombstoning (Phase 3.1 handles local deletion via watcher — no tombstones in local scope)
- Conflict resolution (Phase 3.4)

---

## Component breakdown

### `ChunkRecord` and LanceDB schema

Add `is_tombstone: bool = False` to `vdb.ChunkRecord` and to `vdb.py:_schema()`:

```python
pa.field("is_tombstone", pa.bool_()),
```

Default `False` — existing chunks are not tombstoned. LanceDB `merge_insert` preserves the field on upsert.

### pgvector schema

Add `is_tombstone BOOLEAN NOT NULL DEFAULT FALSE` to the `CREATE TABLE IF NOT EXISTS` statement in `PgvectorDriver.ensure_collection()`. Update `upsert()` and `query()` accordingly:

```sql
-- query: exclude tombstoned chunks
WHERE true AND is_tombstone = FALSE {where_clause}
```

### `promote.py` — tombstone detection

After loading the local VDB chunk set and before writing new chunks to the global scope, detect deletions by index comparison:

```python
# Paths currently in local VDB
local_paths = {chunk["path"] for chunk in all_local_chunks}

# Paths previously promoted to global by this project
global_paths = {row["path"] for row in central_vdb.query_all_paths(cfg.project.id)}

deleted_paths = global_paths - local_paths

for path in deleted_paths:
    # VDB: mark all chunks for path as tombstoned
    central_vdb.tombstone_path(cfg.project.id, path)
    # KG: set tombstoned_at on node
    central_kg.set_tombstoned(path, timestamp=now_iso())

console.print(f"  tombstoned: {len(deleted_paths)} deleted path(s)")
```

`--dry-run` reports `deleted_paths` without writing.

New driver methods required:
- `PgvectorDriver.query_all_paths(project_id)` — returns all distinct paths in global scope for this project
- `PgvectorDriver.tombstone_path(project_id, path)` — sets `is_tombstone=True` on all chunks for path
- `Neo4jDriver.set_tombstoned(path, timestamp)` — sets `tombstoned_at` on node

### Recall hooks — tombstone filter

In all global VDB and KG queries within `preload.py`, `user_prompt_submit.py`, and `recall.py`, add tombstone exclusion:

```python
# VDB: pass where filter to central driver query
global_hits = central_vdb.query(cfg.project.id, embedding=embedding, k=k, where="is_tombstone = FALSE")

# KG: add to Cypher
"MATCH (a:Artifact) WHERE a.tombstoned_at = '' ..."
```

### `commands/gc.py` — new command

```
cartographer gc [--dry-run] [--older-than <days>]
```

Default retention: 30 days.

```python
def run(path, dry_run, older_than):
    # 1. Query global VDB for is_tombstone=True AND updated_at < cutoff
    # 2. Delete those chunks from pgvector
    # 3. Query global KG for tombstoned_at < cutoff
    # 4. DETACH DELETE those nodes
    # 5. Report counts; exit 0
```

Register `gc` in `cli/src/cartographer/cli.py`.

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Deleting a file on a branch and promoting marks it as `is_tombstone=True` in the global VDB | Delete; promote; query pgvector directly; confirm `is_tombstone=True` on affected chunks |
| 2 | Deleted artifact's KG node has `tombstoned_at` set after promote | Delete; promote; query Neo4j; confirm `tombstoned_at` is a non-empty timestamp |
| 3 | Tombstoned artifacts do not appear in global VDB recall results | Tombstone an artifact; run `cartographer recall`; confirm it is absent |
| 4 | Tombstoned artifacts do not appear in KG neighbor traversal results | Tombstone a node; run a KG neighbors query; confirm tombstoned node is absent |
| 5 | `cartographer gc --older-than 0` removes tombstoned artifacts immediately | Tombstone; run gc; query pgvector and Neo4j; confirm artifact is deleted |
| 6 | `cartographer gc --dry-run` reports but does not write | Run dry-run; confirm report; confirm artifact still present in index |
| 7 | `cartographer promote` is idempotent with tombstone detection | Promote twice; stats must be identical after both runs |
| 8 | Existing `cli/tests/test_recall_global.py` (8 tests) still pass | `python -m pytest cli/tests/test_recall_global.py` |
| 9 | Phase 3.1 exit criteria still pass | Run watcher tests |

---

## Test approach

### Unit tests

- `vdb.delete_by_path` still works after `is_tombstone` field added (schema migration)
- `promote.py` tombstone detection: `global_paths - local_paths` correctly identifies deleted paths
- `promote.py --dry-run`: reports deleted paths, writes nothing
- `PgvectorDriver.tombstone_path`: sets `is_tombstone=True` on all chunks for path
- `gc` retention filter: only tombstones older than `--older-than` threshold are returned

### Integration tests (require pgvector + Neo4j)

- Promote an artifact; delete it locally; promote again; confirm `is_tombstone=True` in pgvector and `tombstoned_at` set in Neo4j
- Run `cartographer recall` after tombstone; confirm artifact absent from results
- Run `cartographer gc --older-than 0`; confirm artifact deleted from both backends
- Run `cartographer promote` twice; confirm counts identical

---

*Previous pass: [Phase 3.1 — Watcher Local Cleanup](phase-3.1-watcher-local-cleanup.md)*  
*Next pass: [Phase 3.3 — Rename Tracking](phase-3.3-rename-tracking.md)*
