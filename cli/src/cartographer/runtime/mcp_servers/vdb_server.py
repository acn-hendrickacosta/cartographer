#!/usr/bin/env python3
"""Cartographer VDB MCP server.

Exposes five tools over the MCP stdio protocol:
  - vdb_ensure_collection
  - vdb_upsert
  - vdb_query
  - vdb_delete
  - vdb_collection_stats

Requires the MCP Python SDK: pip install mcp
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError as exc:
    sys.stderr.write(f"mcp SDK not installed: {exc}\n")
    sys.exit(1)

from cartographer import config as config_mod
from cartographer.indexing import vdb as vdb_driver

workspace = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()
cfg = config_mod.load_config(workspace) if config_mod.config_exists(workspace) else None
local_dir = workspace / ".cartographer" / "local"
vdb_path = local_dir / "vdb.lance"

server = Server("cartographer-vdb")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="vdb_ensure_collection",
            description="Ensure the VDB collection exists for the given scope. Idempotent.",
            inputSchema={
                "type": "object",
                "properties": {"scope": {"type": "string", "enum": ["local", "global"]}},
                "required": ["scope"],
            },
        ),
        Tool(
            name="vdb_upsert",
            description="Upsert up to 500 pre-embedded chunks. Keyed on chunk id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["local", "global"]},
                    "chunks": {
                        "type": "array",
                        "maxItems": 500,
                        "items": {
                            "type": "object",
                            "required": ["id", "project_id", "scope", "artifact_type", "path", "text", "embedding", "updated_at"],
                        },
                    },
                },
                "required": ["scope", "chunks"],
            },
        ),
        Tool(
            name="vdb_query",
            description="Semantic search. Returns up to k=50 scored chunks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["local", "global"]},
                    "embedding": {"type": "array", "items": {"type": "number"}},
                    "k": {"type": "integer", "default": 8, "maximum": 50},
                    "where": {"type": "string", "description": "Optional SQL filter"},
                },
                "required": ["scope", "embedding"],
            },
        ),
        Tool(
            name="vdb_delete",
            description="Delete chunks by id list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["local", "global"]},
                    "ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["scope", "ids"],
            },
        ),
        Tool(
            name="vdb_collection_stats",
            description="Return chunk counts per artifact_type for the given scope.",
            inputSchema={
                "type": "object",
                "properties": {"scope": {"type": "string", "enum": ["local", "global"]}},
                "required": ["scope"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import json

    if name == "vdb_ensure_collection":
        scope = arguments["scope"]
        vdb_driver.ensure_collection(vdb_path, scope=scope)
        return [TextContent(type="text", text=json.dumps({"ok": True, "scope": scope}))]

    if name == "vdb_upsert":
        scope = arguments["scope"]
        from cartographer.indexing.vdb import ChunkRecord
        chunks = [ChunkRecord(**c) for c in arguments["chunks"]]
        n = vdb_driver.upsert(vdb_path, scope=scope, chunks=chunks)
        return [TextContent(type="text", text=json.dumps({"upserted": n}))]

    if name == "vdb_query":
        scope = arguments["scope"]
        embedding = arguments["embedding"]
        k = min(int(arguments.get("k", 8)), 50)
        where = arguments.get("where")
        hits = vdb_driver.query(vdb_path, scope=scope, embedding=embedding, k=k, where=where)
        return [TextContent(type="text", text=json.dumps({"results": hits}))]

    if name == "vdb_delete":
        scope = arguments["scope"]
        vdb_driver.delete(vdb_path, scope=scope, ids=arguments["ids"])
        return [TextContent(type="text", text=json.dumps({"ok": True}))]

    if name == "vdb_collection_stats":
        scope = arguments["scope"]
        from lancedb import connect
        counts: dict[str, int] = {}
        try:
            db = connect(str(vdb_path))
            if scope in db.list_tables().tables:
                tbl = db.open_table(scope)
                for row in tbl.to_arrow().to_pylist():
                    atype = row.get("artifact_type", "unknown")
                    counts[atype] = counts.get(atype, 0) + 1
        except Exception:
            pass
        return [TextContent(type="text", text=json.dumps({"scope": scope, "counts": counts}))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main_sync():
    """Synchronous entry point for the pyproject.toml `cartographer-vdb-server` script."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
