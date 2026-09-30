#!/usr/bin/env python3
"""Cartographer KG MCP server.

Runs in two modes:
  stdio (default) — spawned per-session, workspace from CARTO_WORKSPACE env.
  http  (--http)  — long-running localhost server. Workspace resolved from:
                    1. workspace tool argument (Claude passes this from CLAUDE.md)
                    2. ?workspace= query parameter (per-project .mcp.json URL)
                    3. CARTO_WORKSPACE env var

Tools:
  - kg_query     : execute a read-only Cypher query
  - kg_neighbors : get neighboring nodes of an artifact
  - kg_stats     : node and edge counts

HTTP mode also exposes two plain REST routes (Phase 3.1.1):
  - GET  /health      : liveness probe used by `cartographer seed` to detect
                        whether a `cartographer serve` instance is running.
  - POST /api/ingest   : run the ingestion pipeline for a set of paths inside
                        this process. This process is the designated KG write
                        owner (it also runs the watcher, --watch), so routing
                        `cartographer seed` through here instead of opening
                        the KG directly from a second process avoids Kuzu's
                        exclusive-lock conflict. See
                        docs/phases/phase-3.1.1-management-server.md.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextvars import ContextVar
from pathlib import Path

try:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        from mcp.server.mcpserver import MCPServer
except ImportError as exc:
    sys.stderr.write(f"mcp SDK not installed: {exc}\n")
    sys.exit(1)

# Set by HTTP middleware when ?workspace= is in the URL. Empty string = not set.
_url_workspace: ContextVar[str] = ContextVar("url_workspace", default="")

_ENV_WORKSPACE = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()

mcp = MCPServer("cartographer-kg")


def _resolve_workspace(explicit: str = "") -> Path:
    """Resolve workspace: explicit arg → URL param → env var."""
    if explicit:
        return Path(explicit).resolve()
    url_ws = _url_workspace.get()
    if url_ws:
        return Path(url_ws).resolve()
    return _ENV_WORKSPACE


SCOPE_WRITE_FORBIDDEN = "SCOPE_WRITE_FORBIDDEN"


def _check_scope_write(workspace: Path, scope: str, promotion_token: str) -> str | None:
    """Return a SCOPE_WRITE_FORBIDDEN error string if a global-scope write is not authorized.

    Enforcement point for Phase 2 scope write protection (DATA_MODEL.md §6.1).
    Any tool that writes to global scope MUST call this before writing. If it returns
    a non-None string, the tool must return that string immediately without writing.

    All current KG tools are read-only. This function is the guard for future write tools.
    """
    if scope != "global":
        return None
    try:
        from cartographer import config as config_mod
        override = config_mod.load_local_override(workspace)
        if override.promotion_token and override.promotion_token == promotion_token:
            return None
    except Exception:
        pass
    return json.dumps({"error": SCOPE_WRITE_FORBIDDEN, "detail": "Global scope writes require a valid promotion token. Use 'cartographer promote' to write to global scope."})


@mcp.tool()
def kg_query(cypher: str, workspace: str = "") -> str:
    """Execute a read-only Cypher query on the knowledge graph.

    The graph has Artifact nodes and RelatesTo edges.
    Artifact properties: id, project_id, scope, type, path, attrs.
    RelatesTo properties: type (e.g. imports, implements_spec, depends_on), scope, attrs.

    Example queries:
      MATCH (a:Artifact {type: 'spec'}) RETURN a.path LIMIT 10
      MATCH (a:Artifact)-[r:RelatesTo]->(b:Artifact) WHERE a.path CONTAINS 'logo' RETURN a.path, r.type, b.path LIMIT 20

    Args:
        cypher: A Cypher query string. Read-only (MATCH/RETURN only).
        workspace: Absolute path to the project root. Always pass this (see CLAUDE.md).
    """
    try:
        from cartographer.indexing import kg as kg_driver

        ws = _resolve_workspace(workspace)
        kg_path = ws / ".cartographer" / "local" / "kg.kuzu"
        if not kg_path.exists():
            return json.dumps({"error": f"Local KG not found at {kg_path}. Run: cartographer seed ."})
        rows = kg_driver.query(kg_path, cypher)
        return json.dumps({"results": rows}, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def kg_neighbors(node_id: str, workspace: str = "", depth: int = 1, scope: str = "local") -> str:
    """Get neighboring artifact nodes connected to the given node.

    Args:
        node_id: The artifact node id (usually the file path).
        workspace: Absolute path to the project root. Always pass this (see CLAUDE.md).
        depth: Traversal depth 1-4 (default 1).
        scope: Filter by scope — "local" or "global".
    """
    try:
        from cartographer.indexing import kg as kg_driver

        ws = _resolve_workspace(workspace)
        kg_path = ws / ".cartographer" / "local" / "kg.kuzu"
        if not kg_path.exists():
            return json.dumps({"error": f"Local KG not found at {kg_path}. Run: cartographer seed ."})
        rows = kg_driver.neighbors(
            kg_path,
            node_id=node_id,
            depth=min(int(depth), 4),
            scope=scope,
        )
        return json.dumps({"node_id": node_id, "neighbors": rows}, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def kg_stats(workspace: str = "") -> str:
    """Return node and edge counts in the local knowledge graph.

    Args:
        workspace: Absolute path to the project root. Always pass this (see CLAUDE.md).
    """
    try:
        from cartographer.indexing import kg as kg_driver

        ws = _resolve_workspace(workspace)
        kg_path = ws / ".cartographer" / "local" / "kg.kuzu"
        if not kg_path.exists():
            return json.dumps({"error": f"Local KG not found at {kg_path}. Run: cartographer seed ."})
        node_count = kg_driver.query(kg_path, "MATCH (a:Artifact) RETURN count(*) AS cnt")
        edge_count = kg_driver.query(kg_path, "MATCH ()-[r:RelatesTo]->() RETURN count(*) AS cnt")
        return json.dumps({
            "workspace": str(ws),
            "nodes": node_count[0]["cnt"] if node_count else 0,
            "edges": edge_count[0]["cnt"] if edge_count else 0,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def _health(request):
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "pid": os.getpid(), "watch": _watch_enabled})


async def _api_ingest(request):
    from starlette.responses import JSONResponse

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid JSON body"}, status_code=422)

    workspace = body.get("workspace", "")
    paths = body.get("paths", [])
    scope = body.get("scope", "local")
    enrich = bool(body.get("enrich", False))

    if not workspace or not paths:
        return JSONResponse({"detail": "workspace and paths are required"}, status_code=422)

    from cartographer import config as config_mod, registry

    ws = Path(workspace).resolve()
    if not config_mod.config_exists(ws):
        return JSONResponse({"detail": f"no cartographer.toml found at {ws}"}, status_code=422)

    try:
        cfg = config_mod.load_config(ws)
    except Exception as exc:
        return JSONResponse({"detail": f"failed to load config: {exc}"}, status_code=422)

    if registry.get_project(cfg.project.id) is None:
        return JSONResponse(
            {"detail": "project not registered; run 'cartographer init' first"}, status_code=422
        )

    try:
        from cartographer.ingestion.embedder import get_embedder
        embedder = get_embedder()
    except ImportError as exc:
        return JSONResponse({"detail": f"embedder not available: {exc}"}, status_code=422)

    from cartographer.ingestion.pipeline import ingest_paths as run_ingest
    from cartographer.runtime.watcher import INGEST_LOCK

    local_dir = ws / ".cartographer" / "local"
    file_paths = [Path(p) for p in paths]

    with INGEST_LOCK:
        result = run_ingest(
            file_paths,
            project_id=cfg.project.id,
            workspace_root=ws,
            vdb_path=local_dir / "vdb.lance",
            kg_path=local_dir / "kg.kuzu",
            scope=scope,
            embedder=embedder,
            enrich=enrich,
        )

    return JSONResponse({
        "files_processed": result.files_processed,
        "files_skipped": result.files_skipped,
        "chunks_upserted": result.chunks_upserted,
        "nodes_upserted": result.nodes_upserted,
        "edges_upserted": result.edges_upserted,
        "errors": result.errors,
    })


# Set once per process before the app is built; read by the /health route.
# Plain module global, not a ContextVar: this is process-wide startup config,
# not per-request state.
_watch_enabled: bool = False


def _build_http_app(watch: bool = False):
    """Build the Starlette app for HTTP mode. Split out from _run_http so tests
    can exercise /health and /api/ingest with starlette.testclient without
    starting uvicorn or the watcher thread."""
    global _watch_enabled
    from starlette.middleware.base import BaseHTTPMiddleware

    _watch_enabled = watch

    class WorkspaceMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            ws = request.query_params.get("workspace", "")
            token = _url_workspace.set(ws)
            try:
                return await call_next(request)
            finally:
                _url_workspace.reset(token)

    app = mcp.streamable_http_app()
    app.add_middleware(WorkspaceMiddleware)
    app.add_route("/health", _health, methods=["GET"])
    app.add_route("/api/ingest", _api_ingest, methods=["POST"])
    return app


def _run_http(port: int, watch: bool = False) -> None:
    """Run as a persistent HTTP server with per-request workspace routing.

    When watch=True, this process also runs the background filesystem watcher
    (see runtime/watcher.py) and becomes the sole KG write owner for every
    registered project — all ingestion (watcher-driven and delegated
    `cartographer seed` requests) happens through this one process, so Kuzu's
    per-path exclusive lock is only ever held here.
    """
    import uvicorn

    app = _build_http_app(watch=watch)

    watch_stop = threading.Event()
    watch_thread: threading.Thread | None = None
    if watch:
        from cartographer.runtime.watcher import watch_projects
        watch_thread = threading.Thread(target=watch_projects, args=(watch_stop,), daemon=True)
        watch_thread.start()

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        watch_stop.set()
        if watch_thread is not None:
            watch_thread.join(timeout=5)


def main_sync() -> None:
    args = sys.argv[1:]
    if "--http" in args:
        port = 4011
        if "--port" in args:
            port = int(args[args.index("--port") + 1])
        watch = "--watch" in args
        _run_http(port, watch=watch)
    else:
        mcp.run()


if __name__ == "__main__":
    main_sync()
