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
  - kg_impact    : reverse-traversal impact analysis, local or cross-project (Phase 4)

HTTP mode also exposes plain REST routes so other CLI commands can delegate
KG access to this process instead of opening kg.kuzu themselves — once this
process (running --watch) has done one write, it holds Kuzu's exclusive
write lock for its entire lifetime, so any other opener (write or read) would
otherwise be permanently blocked:
  - GET  /health       : liveness probe used by delegating commands to detect
                        whether a `cartographer serve` instance is running.
  - POST /api/ingest    : run the ingestion pipeline for a set of paths.
                        Delegation target for `cartographer seed` (Phase 3.1.1).
  - POST /api/query     : run a read-only Cypher query.
  - POST /api/neighbors : get neighboring nodes of an artifact.
                        Delegation target for `cartographer ui`'s
                        /api/graph, /api/files, /api/stats routes
                        (Phase 3.1.2). See
                        docs/phases/phase-3.1.1-management-server.md and
                        docs/phases/phase-3.1.2-ui-read-delegation.md.
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


@mcp.tool()
def kg_impact(
    node_id: str,
    workspace: str = "",
    max_depth: int = 4,
    edge_types: str = "calls,imports,extends",
    scope: str = "global",
) -> str:
    """Return all artifacts that transitively depend on the given node.

    Use this to answer: "what breaks if I change this function/class/module?"
    Traverses calls, imports, and extends edges in reverse (callers of callee,
    importers of module, subclasses of class). Excludes tombstoned (deleted)
    dependents.

    Args:
        node_id: The artifact node id (usually file path or file::symbol).
        workspace: Absolute path to project root. Always pass this (see CLAUDE.md).
        max_depth: Maximum traversal depth 1-6 (default 4).
        edge_types: Comma-separated edge types to traverse in reverse.
        scope: "global" to traverse across all promoted projects (default), "local" for this project only.
    """
    try:
        ws = _resolve_workspace(workspace)
        depth = max(1, min(int(max_depth), 6))
        types = [t.strip() for t in edge_types.split(",") if t.strip()]

        if scope == "local":
            from cartographer.indexing import kg as kg_driver

            kg_path = ws / ".cartographer" / "local" / "kg.kuzu"
            if not kg_path.exists():
                return json.dumps({"error": f"Local KG not found at {kg_path}. Run: cartographer seed ."})
            rows = kg_driver.impact(kg_path, node_id=node_id, depth=depth, edge_types=types)
            return json.dumps({"node_id": node_id, "scope": "local", "impact": rows}, default=str)

        from cartographer import config as config_mod
        from cartographer.indexing.central import get_central_kg

        if not config_mod.config_exists(ws):
            return json.dumps({"error": f"no cartographer.toml found at {ws}"})
        cfg = config_mod.load_config(ws)
        if cfg.topology.mode != "central":
            return json.dumps({"error": "kg_impact with scope='global' requires topology.mode = 'central'; use scope='local' instead"})
        override = config_mod.load_local_override(ws)
        central_kg = get_central_kg(cfg, override)
        if not central_kg.is_reachable():
            return json.dumps({"error": "central KG (Neo4j) is not reachable"})
        # Federated overlays: this project's own data plus any projects it has
        # explicitly opted into reading (cfg.federation.global_overlays).
        # Every promoted project shares one physical Neo4j graph with no
        # structural partitioning, so this is the isolation boundary, not an
        # optional extra.
        allowed_projects = [cfg.project.id, *cfg.federation.global_overlays]
        rows = central_kg.find_impact(node_id, depth=depth, edge_types=types, project_ids=allowed_projects)
        return json.dumps({"node_id": node_id, "scope": "global", "impact": rows}, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def _health(request):
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "pid": os.getpid(), "watch": _watch_enabled})


def _resolve_kg_path(workspace: str):
    """Shared workspace → kg_path resolution for the /api/* routes.

    Returns (kg_path, error_response). error_response is None on success.
    """
    from starlette.responses import JSONResponse

    if not workspace:
        return None, JSONResponse({"detail": "workspace is required"}, status_code=422)

    ws = Path(workspace).resolve()
    from cartographer import config as config_mod
    if not config_mod.config_exists(ws):
        return None, JSONResponse({"detail": f"no cartographer.toml found at {ws}"}, status_code=422)

    kg_path = ws / ".cartographer" / "local" / "kg.kuzu"
    if not kg_path.exists():
        return None, JSONResponse({"detail": f"no local KG at {kg_path}"}, status_code=422)

    return kg_path, None


async def _api_query(request):
    """Run a read-only Cypher query inside this process — reuses whatever
    kuzu.Database handle this process already has cached (kg.py's
    _rw_db_cache / _ro_db_cache), so it never competes for the KG lock with
    the watcher or with itself. Delegation target for `cartographer ui`'s
    /api/graph, /api/files, /api/stats routes (Phase 3.1.2)."""
    from starlette.responses import JSONResponse

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid JSON body"}, status_code=422)

    cypher = body.get("cypher", "")
    if not cypher:
        return JSONResponse({"detail": "cypher is required"}, status_code=422)

    kg_path, error = _resolve_kg_path(body.get("workspace", ""))
    if error is not None:
        return error

    from cartographer.indexing import kg as kg_driver

    try:
        rows = kg_driver.query(kg_path, cypher, body.get("params") or {})
    except Exception as exc:
        status = 503 if "lock" in str(exc).lower() else 500
        return JSONResponse({"detail": str(exc)}, status_code=status)

    return JSONResponse({"results": rows})


async def _api_neighbors(request):
    """Delegation target for `cartographer ui`'s /api/graph route (Phase 3.1.2)."""
    from starlette.responses import JSONResponse

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "invalid JSON body"}, status_code=422)

    node_id = body.get("node_id", "")
    if not node_id:
        return JSONResponse({"detail": "node_id is required"}, status_code=422)

    kg_path, error = _resolve_kg_path(body.get("workspace", ""))
    if error is not None:
        return error

    from cartographer.indexing import kg as kg_driver

    try:
        rows = kg_driver.neighbors(
            kg_path,
            node_id=node_id,
            depth=min(int(body.get("depth", 1)), 4),
            scope=body.get("scope"),
        )
    except Exception as exc:
        status = 503 if "lock" in str(exc).lower() else 500
        return JSONResponse({"detail": str(exc)}, status_code=status)

    return JSONResponse({"neighbors": rows})


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
    strict = bool(body.get("strict", False))

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
            strict=strict,
        )

    return JSONResponse({
        "files_processed": result.files_processed,
        "files_skipped": result.files_skipped,
        "chunks_upserted": result.chunks_upserted,
        "nodes_upserted": result.nodes_upserted,
        "edges_upserted": result.edges_upserted,
        "errors": result.errors,
        "taxonomy_warnings": result.taxonomy_warnings,
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
    app.add_route("/api/query", _api_query, methods=["POST"])
    app.add_route("/api/neighbors", _api_neighbors, methods=["POST"])
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
