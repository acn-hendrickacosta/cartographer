# Implementation plan: Phase 2 global recall in `recall.py`

**Status:** Pending  
**Spec:** `cli/tests/test_recall_global.py` (3 RED tests gate this work)  
**Reference implementation:** `cli/src/cartographer/runtime/scripts/user_prompt_submit.py`

The `cartographer recall` command currently only queries the local index. In central
topology, it must also query the central VDB (pgvector), merge results local-first,
tag each result with its origin, and degrade gracefully if the central backend is
unreachable. `user_prompt_submit.py` already has this exact pattern; `recall.py`
adopts it.

---

## File to edit

`cli/src/cartographer/commands/recall.py`

---

## Step 1 — Load the local override config

After `cfg = config_mod.load_config(workspace)` (line 31), load the override so
the central factory has the connection credentials:

```python
override = config_mod.load_local_override(workspace)
```

`load_local_override` returns a safe default if `.cartographer.local.toml` does not
exist — no guard needed.

---

## Step 2 — Keep the local VDB query, capture its results

Rename the existing assignment on line 66 so the result is available for merging:

```python
local_hits = vdb.query(local_dir / "vdb.lance", scope="local", embedding=embedding, k=k)
```

---

## Step 3 — Conditionally query the central VDB

After the local query, add a block gated on topology. Wrap in `try/except` so a
connection error or missing credentials degrades gracefully instead of crashing.

```python
global_hits: list[dict] = []
if cfg.topology.mode == "central":
    try:
        from cartographer.indexing.central import get_central_vdb
        central_vdb = get_central_vdb(cfg, override)
        if central_vdb.is_reachable():
            global_hits = central_vdb.query(cfg.project.id, embedding=embedding, k=k)
            for h in global_hits:
                h["origin"] = "global"
        else:
            console.print("[yellow]central index unreachable — showing local results only[/yellow]")
    except Exception:
        console.print("[yellow]central index unavailable — showing local results only[/yellow]")
```

`PgvectorDriver.query(project_id, embedding, k)` is the driver signature —
`cfg.project.id` is the first positional argument.

---

## Step 4 — Merge: local shadows global by artifact path

This is the rule from `DATA_MODEL.md`: local results always shadow global results
for the same artifact path, regardless of score. Unmerged working state takes
precedence over the last-promoted version.

```python
local_paths = {h.get("path") for h in local_hits}
merged_vdb = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]
```

---

## Step 5 — Print results with origin tags

Replace the current per-hit print loop with one that reads the `origin` field
(defaults to `"local"` if absent, matching `user_prompt_submit.py`):

```python
console.print(f"VDB matches: {len(merged_vdb)}")
for hit in merged_vdb:
    origin = hit.get("origin", "local")
    console.print(
        f"  - [{hit.get('artifact_type', 'code')}|{origin}] "
        f"{hit['path']} :: {hit['text'][:80]}"
    )
```

---

## What does NOT change

| Area | Reason |
|---|---|
| Local KG query | Central KG query is a follow-up; not required to pass the 3 RED tests |
| Tenant isolation gate (lines 36–40) | Already correct — fires before any query |
| Local topology behaviour | The `if cfg.topology.mode == "central"` gate ensures zero central calls |

---

## Acceptance criteria

Run the spec after implementing:

```bash
python -m pytest cli/tests/test_recall_global.py -v
```

All 8 tests must be GREEN. The 3 currently RED tests will pass once steps 3–5 are
in place:

| Test | Gated by |
|---|---|
| `test_central_topology_queries_central_vdb` | Step 3 — central VDB called with `project_id` |
| `test_results_tagged_with_origin` | Step 5 — `\|local]` and `\|global]` tags in output |
| `test_local_results_appear_before_global` | Step 4 — merge preserves local-first order |
