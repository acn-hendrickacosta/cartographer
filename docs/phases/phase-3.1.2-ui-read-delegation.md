# Phase 3.1.2 — UI read delegation via KG server

## Problem

Phase 3.1.1 made the KG server subprocess (port 4011, `--watch`) the sole KG write owner: once its watcher does one flush, it caches a read-write `kuzu.Database` handle for the rest of the process's life (`kg.py`'s `_rw_db_cache`). This is correct for that process, but it means **any other process** that tries to open `kg.kuzu` — not just a second writer — is now permanently locked out, not just during a brief flush window.

`cartographer ui` is exactly such a process. Its `/api/graph`, `/api/files`, and `/api/stats` routes open the KG directly (`kg_driver.query`, `kg_driver.neighbors`). While `cartographer serve --watch` is running and has processed at least one file, every one of these UI requests now returns the 503 "Knowledge graph is temporarily locked" response permanently, not intermittently. Confirmed via `lsof`: the kg-server subprocess holds `kg.kuzu` with read-write descriptors plus an active `.wal` file for its entire runtime.

## Solution

Apply the same delegation pattern as `cartographer seed` (Phase 3.1.1): add plain REST query routes to the KG server's existing HTTP app, and have `cartographer ui` delegate to them when serve is reachable.

## Scope

| Component | Change |
|---|---|
| `runtime/mcp_servers/kg_server.py` | Add `POST /api/query` (wraps `kg_driver.query`) and `POST /api/neighbors` (wraps `kg_driver.neighbors`) to the existing Starlette app |
| `ui/server.py` | `/api/graph`, `/api/files`, `/api/stats` check `_serve_reachable(KG_SERVER_PORT)` first; delegate via HTTP when reachable; keep the existing direct-open + 503 fallback for when serve is not running |

Both new routes execute inside the kg-server process, reusing its already-cached `kuzu.Database` handle (via `kg.py`'s `_rw_db_cache`/`_ro_db_cache`) — no new Database object, no lock conflict, regardless of whether the process is currently read-write-locked.

## API

### `POST /api/query`

Request: `{"workspace": str, "cypher": str, "params": dict | null}`
Response: `{"results": [...]}`  (same row shape as `kg_driver.query`)
Errors: `422` for missing fields or unknown workspace; `503` if `kg_driver.query` itself raises a lock error (should not normally happen inside this process, but kept as a safety net).

### `POST /api/neighbors`

Request: `{"workspace": str, "node_id": str, "depth": int, "scope": str | null}`
Response: `{"neighbors": [...]}`

## Out of scope

- Delegating `/api/search` (VDB) — LanceDB does not have Kuzu's exclusive-lock problem; no change needed there.
- A generic MCP client in `cartographer ui` (using the real MCP streamable-HTTP protocol). Plain REST routes are simpler and consistent with the `/api/ingest` precedent from Phase 3.1.1.

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `cartographer ui`'s `/api/graph` succeeds while `serve --watch` holds the KG write lock | Start serve, trigger a watcher flush, start `cartographer ui`, hit `/api/graph`; expect 200, not 503 |
| 2 | `/api/files` and `/api/stats` behave the same way | Same setup; hit both routes |
| 3 | `cartographer ui` still works standalone (serve not running) | Stop serve; run `cartographer ui`; confirm direct-open path still returns correct data |
| 4 | Delegated and direct responses are shape-identical | Compare JSON keys/values between delegated and direct-mode responses for the same query |
| 5 | Unit tests cover: `/api/query` and `/api/neighbors` success, unknown workspace 422, `cartographer ui` delegation vs. direct fallback | `pytest cli/tests/test_management_server.py` (extended) and/or a new `test_ui_delegation.py` |
