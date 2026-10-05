# Phase 3.3: Rename Tracking — Global Index Rename Linking at Promote Time

**Status:** Code complete as of 2026-10-05. All 9 exit criteria verified — 178 unit tests passing (10 new: 5 in `test_promote_rename.py`, 2 redirect tests in `test_recall_global.py`, 3 direct-driver tests) plus 29 integration tests against a live pgvector+Neo4j backend, including a full end-to-end rename-and-promote-twice idempotency check. The redirect design in this doc's original draft assumed tombstoned VDB chunks could still surface in `global_hits` for recall to check — corrected during implementation once that assumption was found to conflict with Phase 3.2's hard tombstone filter; see `recall.py`'s central-KG path-lookup approach instead.

## Goal

When a file is renamed and the branch is promoted, the old artifact identity is linked to the new identity via a `supersedes` edge in the global KG. The old path is tombstoned. Recall follows the `supersedes` chain and returns the new artifact, tagged as `origin: renamed`, rather than returning the tombstoned old path or missing the artifact entirely.

**Entry condition:** Phase 3.2 complete and stable. Tombstone protocol must be working before rename tracking is added — rename tracking reuses tombstone writing for the old path.

---

## References

| Document | What to read |
|---|---|
| [phase-3-protocols/rename-tracking-protocol.md](phase-3-protocols/rename-tracking-protocol.md) | Full rename tracking spec |
| `cli/src/cartographer/commands/promote.py` | Current promote — add git rename detection here |
| `cli/src/cartographer/registry.py` | `ProjectRecord` — add `last_promoted_sha` |

---

## Scope

### In scope

| Component | Change |
|---|---|
| `registry.ProjectRecord` | Add `last_promoted_sha: str = ""` |
| `promote.py` | Git rename detection via `git diff --name-status --diff-filter=R`; write `supersedes` edges; update `last_promoted_sha` after successful promote |
| `kg_neo4j.Neo4jDriver` | No schema change — `supersedes` is a standard `RelatesTo` edge with `type='supersedes'` |
| Recall hooks (`preload.py`, `user_prompt_submit.py`, `recall.py`) | Follow `supersedes` edges from tombstoned nodes; tag result with `origin: renamed` |

### Explicitly out of scope

- Local index rename handling (Phase 3.1 already covers this via watcher `on_moved`)
- `kg_move_node` MCP tool (not needed — `supersedes` edge uses existing `RelatesTo` structure)
- Conflict resolution (Phase 3.4)

---

## Component breakdown

### `registry.ProjectRecord`

```python
class ProjectRecord(BaseModel):
    ...
    last_promoted_sha: str = ""   # git SHA of HEAD at last successful promote
```

Update `promote.py` to write `last_promoted_sha` at the end of a successful run:

```python
import subprocess
try:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
    registry.update_project(project_id, last_promoted_sha=sha)
except Exception:
    pass  # non-git repo or git unavailable; leave as ""
```

### `promote.py` — rename detection

Run before tombstone detection, so renames are correctly separated from pure deletions:

```python
rename_map: dict[str, str] = {}   # {old_path: new_path}
last_sha = record.last_promoted_sha if record else ""

if last_sha:
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-status", "--diff-filter=R", f"{last_sha}..HEAD"],
            cwd=workspace, text=True,
        )
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                rename_map[parts[1]] = parts[2]
    except Exception:
        console.print("[yellow]  git rename detection unavailable; renames treated as delete + add[/yellow]")
```

For each rename, write a `supersedes` edge and tombstone the old path:

```python
for old_path, new_path in rename_map.items():
    central_kg.upsert_edges([Edge(
        src=artifact_id(new_path),
        dst=artifact_id(old_path),
        type="supersedes",
        scope="global",
        attrs=json.dumps({"renamed_from": old_path, "renamed_at": now_iso()}),
    )])
    central_kg.set_tombstoned(old_path, timestamp=now_iso())
    central_vdb.tombstone_path(cfg.project.id, old_path)

# Exclude renamed paths from pure-deletion tombstone detection
deleted_paths = (global_paths - local_paths) - set(rename_map.keys())
```

### Recall hooks — `supersedes` redirect

After merging local and global results, check for tombstoned global results that have an incoming `supersedes` edge. If found, substitute the new artifact:

```python
for hit in global_hits:
    if hit.get("tombstoned_at"):
        # Check for supersedes edge pointing TO this node
        redirect = central_kg.find_supersedes_source(hit["path"])
        if redirect:
            # Fetch the new artifact's content and tag it
            new_hit = central_vdb.query_by_path(cfg.project.id, redirect["new_path"])
            if new_hit:
                new_hit["origin"] = "renamed"
                new_hit["renamed_from"] = hit["path"]
                hit = new_hit
```

New driver methods required:
- `Neo4jDriver.find_supersedes_source(old_path)` — returns `{new_path, renamed_at}` if a `supersedes` edge exists pointing to this path; else `None`
- `PgvectorDriver.query_by_path(project_id, path)` — fetch the most recent chunk for a specific path

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `last_promoted_sha` is written to registry after a successful `cartographer promote` | Promote; inspect registry; confirm `last_promoted_sha` matches `git rev-parse HEAD` |
| 2 | Renaming a file on a branch and promoting writes a `supersedes` edge in the global KG | Rename; promote; query Neo4j for `supersedes` edge from new path to old path; confirm it exists with correct attrs |
| 3 | The old path's KG node has `tombstoned_at` set and VDB chunks have `is_tombstone=True` | After rename + promote; query Neo4j and pgvector directly; confirm tombstone state on old path |
| 4 | The new path's artifact is in the global index with correct content | After rename + promote; run `cartographer recall <query>`; confirm new path appears in results |
| 5 | Recall does not return the tombstoned old path directly | Run recall for old path name; confirm result shows new path (tagged `origin: renamed`), not old tombstoned path |
| 6 | When git history is unavailable, rename falls back to tombstone + add with a warning | Promote from a non-git directory; confirm warning printed; confirm old path tombstoned, new path promoted |
| 7 | Phase 3.2 exit criteria still pass | Run tombstone tests; confirm no regression |
| 8 | Phase 3.1 exit criteria still pass | Run watcher tests |

---

## Test approach

### Unit tests

- `promote.py` rename detection: `git diff` output parsed correctly into `rename_map`
- `promote.py`: renamed paths excluded from pure-deletion tombstone detection
- `promote.py`: `supersedes` edge written with correct `renamed_from` and `renamed_at` attrs
- `promote.py`: `last_promoted_sha` updated on success; not updated on failure
- Recall hook: tombstoned hit with `supersedes` edge is substituted with new artifact tagged `origin: renamed`
- Recall hook: tombstoned hit with no `supersedes` edge is excluded (not substituted)

### Integration tests (require pgvector + Neo4j + git repo)

- Rename a file; promote; query Neo4j for `supersedes` edge; query pgvector for old path `is_tombstone=True`
- Run `cartographer recall` for old path term; confirm new path returned tagged `origin: renamed`
- Promote again (idempotent); confirm `supersedes` edge not duplicated; counts unchanged

---

*Previous pass: [Phase 3.2.1 — Serve Process Lifecycle](phase-3.2.1-serve-process-lifecycle.md)*  
*Next pass: [Phase 3.4 — Conflict Resolution](phase-3.4-conflict-resolution.md)*
