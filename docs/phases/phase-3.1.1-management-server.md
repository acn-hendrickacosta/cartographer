# Phase 3.1.1 — Ingest delegation via KG server (port 4011)

## Problem

`cartographer serve` creates three competing KG openers:

| Process | KG access needed | Lock type |
|---|---|---|
| Main `serve` process | Watcher `_flush_ready` | Read-write (exclusive) |
| `cartographer-kg-server` subprocess (port 4011) | MCP query tools | Read attempted |
| `cartographer seed` | Bulk ingest | Read-write (exclusive) |

Kuzu's file lock is exclusive when any opener is read-write. The watcher in the main process holds the write lock, blocking both the KG server subprocess and any concurrent `cartographer seed`.

Adding a third port would add complexity without fixing the root cause. The root cause is that KG write access is split across two processes (main serve + kg-server subprocess). The fix is to consolidate.

## Solution

Move the watcher from the main `serve` process into the `cartographer-kg-server` subprocess. Add `GET /health` and `POST /api/ingest` to the kg-server's existing HTTP app (port 4011). Now one process owns the KG exclusively.

```
cartographer serve (main process — no KG access)
├── subprocess: cartographer-vdb-server --http --port 4010
└── subprocess: cartographer-kg-server --http --port 4011 --watch
                ├── watcher thread  ──► ingest_paths()  ┐
                ├── POST /api/ingest ──► ingest_paths()  ├── one shared kuzu.Database
                └── MCP tools (kg_query, etc.)  ────────┘

cartographer seed
  └── GET  127.0.0.1:4011/health → 200   # serve is running
  └── POST 127.0.0.1:4011/api/ingest     # delegate, no lock conflict
```

When `serve` is not running, `seed` opens the KG directly as it does today.

## Scope

| Component | Change |
|---|---|
| `runtime/mcp_servers/kg_server.py` | Add `--watch` CLI flag; start watcher thread in `_run_http()`; add `GET /health` and `POST /api/ingest` routes to the existing Starlette app |
| `commands/serve.py` | Pass `--watch` to `cartographer-kg-server` subprocess; remove `watch_projects` thread from main process |
| `commands/seed.py` | Before opening KG directly: check `GET http://127.0.0.1:{kg_port}/health`; if alive, POST to `/api/ingest` and display result |
| `cartographer.toml` schema | No new keys needed — `kg_port` is already the configured port |

## kg-server changes

### New CLI flag

```
cartographer-kg-server --http [--port 4011] [--watch]
```

`--watch` starts the watcher thread inside the kg-server process after uvicorn is running. Off by default — stdio invocations (spawned per-session by Claude Code) must not start a watcher.

### New routes on the existing Starlette app

```python
app = mcp.streamable_http_app()
app.add_middleware(WorkspaceMiddleware)
app.add_route("/health", health_handler)          # GET
app.add_route("/api/ingest", ingest_handler, methods=["POST"])  # POST
```

#### `GET /health`

```json
{ "status": "ok", "pid": 12345, "watch": true }
```

#### `POST /api/ingest`

Request:
```json
{
  "workspace": "/abs/path/to/project",
  "paths":     ["/abs/path/to/file.py"],
  "scope":     "local",
  "enrich":    false
}
```

Response (synchronous — waits for ingestion):
```json
{
  "files_processed": 12,
  "files_skipped":    1,
  "chunks_upserted":  87,
  "nodes_upserted":   12,
  "edges_upserted":   34,
  "errors":           []
}
```

Ingestion is serialized by a `threading.Lock` shared with the watcher flush path. Concurrent POST requests queue. The lock ensures the watcher and a delegated seed never call `ingest_paths` simultaneously for the same project.

### Thread model inside kg-server (HTTP mode with --watch)

```
cartographer-kg-server (--http --watch)
├── uvicorn worker threads  (MCP tools + /health + /api/ingest)
├── watcher thread          (DirtyTracker + watchdog Observer)
└── kuzu.Database cache     (_rw_db_cache — one handle shared by all)
```

All paths reach `ingest_paths` through the same `kuzu.Database` handle from `_rw_db_cache`. No second Database object is ever opened for the same path within this process.

## `serve.py` changes

Remove the watcher thread from the main process. Pass `--watch` to the kg-server subprocess:

```python
# Before
procs = [
    subprocess.Popen([vdb_cmd, "--http", "--port", str(vdb_port)]),
    subprocess.Popen([kg_cmd,  "--http", "--port", str(kg_port)]),
]
if watch:
    watch_thread = threading.Thread(target=watch_projects, ...)
    watch_thread.start()

# After
procs = [
    subprocess.Popen([vdb_cmd, "--http", "--port", str(vdb_port)]),
    subprocess.Popen([kg_cmd,  "--http", "--port", str(kg_port)] + (["--watch"] if watch else [])),
]
# No watcher thread in main process
```

## `seed.py` changes

```python
def _kg_port(cfg) -> int:
    return getattr(cfg.serve, "kg_port", 4011)

def _serve_running(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5)
        return True
    except Exception:
        return False
```

Delegation path (serve running):
1. Show spinner: `delegating to cartographer serve (port {port})…`
2. POST `/api/ingest` with `{workspace, paths, scope, enrich}`
3. Print result in same format as direct mode
4. Exit with code 0 on success, 1 on non-200

Direct path (serve not running): unchanged from today.

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | `cartographer-kg-server --http --watch` starts the watcher internally | Check logs; modify a watched file; confirm it is re-ingested without running `serve` |
| 2 | `GET 127.0.0.1:4011/health` returns `{"status":"ok"}` while serve is running | `curl http://127.0.0.1:4011/health` |
| 3 | `cartographer seed` succeeds while `cartographer serve` is running | Run both; confirm seed exits 0 and prints correct counts |
| 4 | Output format is identical whether serve is running or not | Compare `processed / chunks / nodes / edges` lines |
| 5 | `cartographer seed` uses the direct path when serve is not running | Stop serve; run seed; confirm it still works |
| 6 | Watcher flush and seed request never corrupt the index when interleaved | Run seed on a large directory while watcher is active; run `cartographer doctor` after |
| 7 | `POST /api/ingest` with an unregistered workspace returns 422, not 500 | POST with a non-existent workspace; check status code |
| 8 | Main `serve` process no longer holds the KG lock | `lsof` while serve is running: only the kg-server subprocess PID appears against `kg.kuzu` |
| 9 | Unit tests cover: health endpoint, ingest endpoint success, unknown workspace 422, seed delegation, seed direct fallback | `pytest cli/tests/test_management_server.py` passes |

## Entry condition

Phase 3.1 complete.

## Out of scope

- Authentication (localhost-only is sufficient)
- Progress streaming (SSE); synchronous response is sufficient
- `cartographer ui` integration with the ingest endpoint
