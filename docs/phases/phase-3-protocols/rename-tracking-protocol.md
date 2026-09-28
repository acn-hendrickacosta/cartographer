# Rename Tracking Protocol

**Status:** Draft — awaiting review  
**Phase:** 3  
**Blocks:** rename detection in `promote.py`, `supersedes` edge writing, recall redirect

---

## Problem

When a file is renamed and the branch merges, `cartographer promote` currently treats the rename as a delete (old path stays in global forever) plus an add (new path promoted as a new artifact). The old identity accumulates as a ghost with no link to the new identity. Queries against the old path return stale results. Queries against the new path miss all history and relationships that referenced the old path.

---

## Detection strategy

**Primary: git rename detection at promote time.**

Run `git diff --name-status --diff-filter=R <last_promoted_sha>..HEAD` to get a list of rename pairs `(old_path, new_path)` since the last promotion.

This requires tracking the git commit SHA of the last promotion — add `last_promoted_sha: str = ""` to `registry.ProjectRecord`.

At `cartographer promote` start:
1. Read `last_promoted_sha` from registry
2. If set: `git diff --name-status --diff-filter=R <last_promoted_sha>..HEAD`
3. Parse output: `R100\told/path.py\tnew/path.py`
4. Build rename map: `{old_path: new_path}`

**Fallback when git history is unavailable (no `last_promoted_sha`, non-git repo, CI shallow clone):**

Use the tombstone detection path (index comparison). A rename becomes a tombstone on the old path + a new node on the new path — no `supersedes` link. This loses the rename relationship but is safe. A warning is printed: `"git history unavailable; renames treated as delete + add"`.

**Why not content similarity scoring:**
- Too slow at scale (O(n²) comparison)
- Unreliable for large files with many changes
- git already tracks renames reliably with similarity index

---

## Rename record schema

### KG edge

A `supersedes` edge is written from the new artifact node to the old artifact node:

```
(new_node)-[r:RelatesTo {type: 'supersedes'}]->(old_node)
```

Edge attrs:
```json
{"renamed_from": "old/path.py", "renamed_at": "<ISO timestamp>"}
```

The old node is also tombstoned (`tombstoned_at` set) per the tombstone protocol — but its node and edges are preserved for traversal via `supersedes`.

### VDB

All VDB chunks for the old path are tombstoned (`is_tombstone = True`). The new path's chunks are promoted normally as new artifacts.

---

## Promote behavior

```
cartographer promote (with rename support):
  1. Detect renames via git diff → rename_map {old_path: new_path}
  2. For each (old_path, new_path) in rename_map:
       KG: ensure new_node exists (will be promoted in step 5)
       KG: write supersedes edge: new_node → old_node
       KG: set tombstoned_at on old_node
       VDB: tombstone all chunks for old_path
  3. Continue with tombstone detection (index comparison) for remaining deletions
  4. Continue with normal promotion of local artifacts (including new_path)
  5. Report: "tracked N renames" in output
```

---

## Recall redirect behavior

When a recall query returns a tombstoned artifact that has a `supersedes` edge pointing to it (i.e., it was renamed), the recall hook:

1. Detects that the returned node is tombstoned
2. Follows the incoming `supersedes` edge to find the new node
3. Returns the new node's content instead, tagged with `origin: renamed`

Example context tag:
```
[RENAMED] src/old_auth.py → src/auth/login.py (promoted 2026-01-15)
```

Direct queries against the old path via `kg_query` will still find the old node (tombstoned) and its `supersedes` edge, so Claude can navigate the history.

---

## Registry change

Add `last_promoted_sha: str = ""` to `registry.ProjectRecord`. Updated at the end of a successful `cartographer promote` by running `git rev-parse HEAD` and storing the result. If git is not available, leave as `""`.

---

## Data model changes required

| Component | Change |
|---|---|
| `registry.ProjectRecord` | Add `last_promoted_sha: str = ""` |
| `promote.py` | Add git rename detection; write `supersedes` edges; update `last_promoted_sha` |
| `kg.py` / `kg_neo4j.py` | No schema change — `supersedes` is a standard `RelatesTo` edge with `type='supersedes'` |
| Recall hooks | Follow `supersedes` edges for tombstoned results; tag with `origin: renamed` |

---

## Open questions resolved

| Question | Decision |
|---|---|
| Rename detection strategy | git diff primary; index comparison fallback (tombstone + add) |
| KG edge type | `supersedes` — standard `RelatesTo` edge (already in edge taxonomy) |
| Old node fate | Tombstoned but kept; removed by `cartographer gc` after retention period |
| VDB old chunks | Tombstoned per tombstone protocol |
| Registry tracking | `last_promoted_sha` added to `ProjectRecord` |

---

## Exit criteria (from phase spec)

| # | Criterion |
|---|---|
| 2 | Renaming a file and promoting links old identity to new identity via `supersedes` edge |
| 4 | Recall follows `supersedes` redirect; does not return tombstoned old path |
