# Tombstone Protocol

**Status:** Draft — awaiting review  
**Phase:** 3  
**Blocks:** tombstone implementation in `promote.py`, `cartographer gc`, recall hook filtering

---

## Problem

When a file is deleted locally and the branch merges, `cartographer promote` currently re-promotes all local artifacts. It has no awareness of what was previously in the global index, so deleted files are never removed — their nodes, edges, and chunks accumulate indefinitely in the global index. Stale entries pollute Claude's recall context with artifacts that no longer exist.

---

## Detection strategy

**Primary: index comparison at promote time.**

At the start of `cartographer promote`, read the set of paths currently in the local VDB (`local_paths`). Query the global index for the set of paths previously promoted by this project (`global_paths`). The difference `global_paths - local_paths` is the set of deleted paths.

```
deleted_paths = {p for p in global_paths if p not in local_paths}
```

This approach requires no git history, works in all environments (bare clones, CI, zipped repos), and is safe across rebases and force pushes.

**Why not git-based detection (`git diff --diff-filter=D`):**
- Requires tracking the git commit SHA of the last promotion
- Breaks after rebases that rewrite the promoted commit
- Not available in all CI environments
- The index comparison achieves the same result without these constraints

---

## Tombstone record schema

### VDB

Add a `is_tombstone` boolean field to the chunk record schema (default `False`). When a path is tombstoned:
- All existing chunks for that path in the global scope have `is_tombstone` set to `True`
- Their `updated_at` is set to the tombstone timestamp
- The chunks are NOT deleted immediately (retained for `cartographer gc` and audit)

A single sentinel tombstone chunk is written if no chunks exist yet for the path (e.g., a path was promoted by a previous developer but has no chunks left):

| Field | Value |
|---|---|
| `id` | `<project_id>/<path>:tombstone` |
| `artifact_type` | `tombstone` |
| `is_tombstone` | `True` |
| `text` | `""` |
| `embedding` | zero vector |
| `updated_at` | tombstone timestamp |

### KG

Add a `tombstoned_at` attribute to the `Artifact` node (empty string = not tombstoned). When a path is tombstoned:
- Set `tombstoned_at = <ISO timestamp>` on the node
- Do NOT delete the node or its edges immediately — keep for traversal history and `supersedes` chains
- Add a `tombstoned` property to outgoing `RelatesTo` edges: `tombstoned = True`

---

## Promote behavior

```
cartographer promote (with tombstone support):
  1. Read local VDB paths → local_paths
  2. Query global VDB for paths promoted by this project → global_paths
  3. deleted_paths = global_paths - local_paths
  4. For each path in deleted_paths:
       VDB: mark all chunks for path as is_tombstone=True, update updated_at
       KG:  set tombstoned_at on node
  5. Continue with normal promotion of local artifacts
  6. Report: "tombstoned N paths" in output
```

`--dry-run` reports tombstoned paths without writing.

---

## Recall filtering

Both recall hooks (`preload.py`, `retrieve.py`) and MCP tool results must filter tombstoned artifacts:

- **VDB**: add `WHERE is_tombstone = False` (or equivalent filter) to all queries against global scope
- **KG**: add `WHERE a.tombstoned_at = ""` (or `IS NULL`) to all `MATCH` queries against global scope
- **`kg_neighbors`**: skip tombstoned neighbors — do not traverse edges where the destination node is tombstoned

Tombstoned artifacts must never appear in Claude's recall context.

---

## `cartographer gc` command

```
cartographer gc [--dry-run] [--older-than <days>]
```

Removes tombstoned artifacts that have been tombstoned for longer than the retention period.

| Flag | Default | Meaning |
|---|---|---|
| `--older-than <days>` | `30` | Only remove tombstones older than this many days |
| `--dry-run` | off | Report what would be removed without writing |

**Behavior:**
1. Query global VDB for chunks where `is_tombstone = True` AND `updated_at < now - retention`
2. Delete those chunks from VDB
3. Query global KG for nodes where `tombstoned_at` is older than retention
4. `DETACH DELETE` those nodes (cascade-deletes their edges)
5. Report counts

**Why a retention period instead of immediate delete:**
- Gives a recovery window if a file was accidentally deleted and needs to be restored
- Allows `supersedes` chains to remain traversable during a rename transition period
- Matches standard database soft-delete patterns

---

## Data model changes required

| Component | Change |
|---|---|
| `vdb.ChunkRecord` | Add `is_tombstone: bool = False` field |
| `vdb_pgvector.PgvectorDriver` | Add `is_tombstone` column; update `ensure_collection`, `upsert`, `query` |
| `kg.Node` (attrs) | Document `tombstoned_at` as a reserved attr key |
| `promote.py` | Add deletion detection + tombstone writing |
| `commands/gc.py` | New command |
| `vdb_server.py` / `kg_server.py` | Filter tombstoned in all query results |
| `registry.ProjectRecord` | No change needed (detection uses index comparison, not commit SHA) |

---

## Open questions resolved

| Question | Decision |
|---|---|
| Detection strategy | Index comparison (not git diff) — works without git history |
| Immediate vs. soft delete | Soft delete with retention period (default 30 days) |
| Tombstone schema | `is_tombstone` field in VDB; `tombstoned_at` attr in KG |
| Claude visibility | Tombstoned artifacts never shown in recall context |
| Recovery | Reseed the file and re-promote to un-tombstone |

---

## Exit criteria (from phase spec)

| # | Criterion |
|---|---|
| 1 | Deleting a file on a branch and promoting does not leave the artifact permanently in global index — it is tombstoned |
| 3 | `cartographer gc` removes tombstoned artifacts beyond the retention period |
| 4 | Recall does not surface tombstoned artifacts in context |
