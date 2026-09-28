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

mcp = MCPServer("cartographer-kg")


def _resolve_workspace(explicit: str = "") -> Path:
    """Resolve workspace: explicit arg → URL param → env var."""
    if explicit:
        return Path(explicit).resolve()
    url_ws = _url_workspace.get()
    if url_ws:
        return Path(url_ws).resolve()
    return _ENV_WORKSPACE


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
        port = 4011
        if "--port" in args:
            port = int(args[args.index("--port") + 1])
        _run_http(port)
    else:
        mcp.run()


if __name__ == "__main__":
    main_sync()
