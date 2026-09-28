#!/usr/bin/env python3
"""Cartographer VDB MCP server.

Runs in two modes:
  stdio (default) — spawned per-session, workspace from CARTO_WORKSPACE env.
  http  (--http)  — long-running localhost server. Workspace resolved from:
                    1. workspace tool argument (Claude passes this from CLAUDE.md)
                    2. ?workspace= query parameter (per-project .mcp.json URL)
                    3. CARTO_WORKSPACE env var

Tools:
  - vdb_search : semantic search by text query (embeds internally)
  - vdb_stats  : chunk counts per artifact type
"""

from __future__ import annotations

import json
import os
import sys
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

mcp = MCPServer("cartographer-vdb")

# Warm up the embedder at startup so the model is loaded before any tool call.
_embedder = None
try:
    from fastembed import TextEmbedding
    _embedder = TextEmbedding()
except Exception:
    pass


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

    All current VDB tools are read-only. This function is the guard for future write tools.
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
def vdb_search(query: str, workspace: str = "", k: int = 8, scope: str = "local") -> str:
    """Semantic search over the Cartographer knowledge index.

    Returns the top-k most relevant indexed chunks (files, specs, docs) for the query.
    Call this to find context relevant to a concept, module, or task before answering.

    Args:
        query: Natural-language search query.
        workspace: Absolute path to the project root. Always pass this (see CLAUDE.md).
        k: Number of results to return (max 20).
        scope: "local" for local index (default).
    """
    try:
        from cartographer.indexing import vdb as vdb_driver

        ws = _resolve_workspace(workspace)
        vdb_path = ws / ".cartographer" / "local" / "vdb.lance"
        if not vdb_path.exists():
            return json.dumps({"error": f"Local index not found at {vdb_path}. Run: cartographer seed ."})

        embedder = _embedder
        if embedder is None:
            from fastembed import TextEmbedding
            embedder = TextEmbedding()
        embedding = list(next(embedder.embed([query[:512]])))
        k = min(int(k), 20)
        hits = vdb_driver.query(vdb_path, scope=scope, embedding=embedding, k=k)

        results = [
            {
                "path": h.get("path", ""),
                "artifact_type": h.get("artifact_type", ""),
                "text": h.get("text", "")[:800],
                "score": h.get("_distance", None),
            }
            for h in hits
        ]
        return json.dumps({"query": query, "workspace": str(ws), "results": results}, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def vdb_stats(workspace: str = "") -> str:
    """Return chunk counts per artifact type in the local index.

    Use this to understand what is indexed (files, specs, docs) and how many chunks exist.

    Args:
        workspace: Absolute path to the project root. Always pass this (see CLAUDE.md).
    """
    try:
        import lancedb

        ws = _resolve_workspace(workspace)
        vdb_path = ws / ".cartographer" / "local" / "vdb.lance"
        if not vdb_path.exists():
            return json.dumps({"error": f"Local index not found at {vdb_path}. Run: cartographer seed ."})

        import pyarrow.compute as pc

        db = lancedb.connect(str(vdb_path))
        tables = db.list_tables()
        if hasattr(tables, "tables"):
            tables = tables.tables
        counts: dict[str, int] = {}
        total = 0
        for table_name in tables:
            tbl = db.open_table(table_name)
            arrow_tbl = tbl.to_arrow(columns=["artifact_type"])
            col = arrow_tbl.column("artifact_type")
            for val in col.unique().to_pylist():
                mask = pc.equal(col, val)
                n = pc.sum(mask.cast("int64")).as_py()
                atype = val if val is not None else "unknown"
                counts[atype] = counts.get(atype, 0) + n
                total += n
        return json.dumps({"workspace": str(ws), "total_chunks": total, "by_type": counts})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _run_http(port: int) -> None:
    """Run as a persistent HTTP server with per-request workspace routing."""
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware

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
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main_sync() -> None:
    args = sys.argv[1:]
    if "--http" in args:
        port = 4010
        if "--port" in args:
            port = int(args[args.index("--port") + 1])
        _run_http(port)
    else:
        mcp.run()


if __name__ == "__main__":
    main_sync()
