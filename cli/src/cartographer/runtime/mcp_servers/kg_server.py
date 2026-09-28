#!/usr/bin/env python3
"""Cartographer KG MCP server.

Exposes eight tools over the MCP stdio protocol:
  - kg_ensure_namespace
  - kg_upsert_nodes
  - kg_upsert_edges
  - kg_query
  - kg_neighbors
  - kg_delete_nodes
  - kg_delete_edges
  - kg_namespace_stats

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
from cartographer.indexing import kg as kg_driver
from cartographer.indexing.kg import Edge, Node

workspace = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()
local_dir = workspace / ".cartographer" / "local"
kg_path = local_dir / "kg.kuzu"

server = Server("cartographer-kg")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="kg_ensure_namespace",
            description="Create Artifact and RelatesTo tables if absent. Idempotent.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="kg_upsert_nodes",
            description="Upsert artifact nodes. Keyed on node id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "project_id", "scope", "type", "path"],
                        },
                    }
                },
                "required": ["nodes"],
            },
        ),
        Tool(
            name="kg_upsert_edges",
            description="Upsert relationship edges. Dangling edges (missing src/dst) are silently skipped.",
            inputSchema={
                "type": "object",
                "properties": {
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["src", "dst", "type", "scope"],
                        },
                    }
                },
                "required": ["edges"],
            },
        ),
        Tool(
            name="kg_query",
            description="Execute a read-only Cypher query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cypher": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["cypher"],
            },
        ),
        Tool(
            name="kg_neighbors",
            description="Return neighbors of a node up to depth 4.",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "depth": {"type": "integer", "default": 1, "minimum": 1, "maximum": 4},
                    "scope": {"type": "string"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="kg_delete_nodes",
            description="Delete nodes by id list. Cascades to their edges.",
            inputSchema={
                "type": "object",
                "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["ids"],
            },
        ),
        Tool(
            name="kg_delete_edges",
            description="Delete edges by src/dst/type triple.",
            inputSchema={
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                    "type": {"type": "string"},
                },
                "required": ["src", "dst", "type"],
            },
        ),
        Tool(
            name="kg_namespace_stats",
            description="Return node and edge counts.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import json

    if name == "kg_ensure_namespace":
        kg_driver.ensure_namespace(kg_path)
        return [TextContent(type="text", text=json.dumps({"ok": True}))]

    if name == "kg_upsert_nodes":
        nodes = [Node(**n) for n in arguments["nodes"]]
        kg_driver.upsert_nodes(kg_path, nodes)
        return [TextContent(type="text", text=json.dumps({"upserted": len(nodes)}))]

    if name == "kg_upsert_edges":
        edges = []
        for e in arguments["edges"]:
            try:
                edges.append(Edge(**e))
            except Exception:
                pass  # dangling edge skipped
        kg_driver.upsert_edges(kg_path, edges)
        return [TextContent(type="text", text=json.dumps({"upserted": len(edges)}))]

    if name == "kg_query":
        rows = kg_driver.query(kg_path, arguments["cypher"], arguments.get("params"))
        return [TextContent(type="text", text=json.dumps({"results": rows}))]

    if name == "kg_neighbors":
        rows = kg_driver.neighbors(
            kg_path,
            node_id=arguments["node_id"],
            depth=min(int(arguments.get("depth", 1)), 4),
            scope=arguments.get("scope"),
        )
        return [TextContent(type="text", text=json.dumps({"nodes": rows}))]

    if name == "kg_delete_nodes":
        conn = kg_driver._connect(kg_path)
        for nid in arguments["ids"]:
            try:
                conn.execute("MATCH (a:Artifact {id: $id}) DELETE a", {"id": nid})
            except Exception:
                pass
        return [TextContent(type="text", text=json.dumps({"ok": True}))]

    if name == "kg_delete_edges":
        conn = kg_driver._connect(kg_path)
        try:
            conn.execute(
                "MATCH (s:Artifact {id: $src})-[r:RelatesTo {type: $type}]->(d:Artifact {id: $dst}) DELETE r",
                {"src": arguments["src"], "dst": arguments["dst"], "type": arguments["type"]},
            )
        except Exception:
            pass
        return [TextContent(type="text", text=json.dumps({"ok": True}))]

    if name == "kg_namespace_stats":
        try:
            node_count = kg_driver.query(kg_path, "MATCH (a:Artifact) RETURN count(*) AS cnt")
            edge_count = kg_driver.query(kg_path, "MATCH ()-[r:RelatesTo]->() RETURN count(*) AS cnt")
            return [TextContent(type="text", text=json.dumps({
                "nodes": node_count[0]["cnt"] if node_count else 0,
                "edges": edge_count[0]["cnt"] if edge_count else 0,
            }))]
        except Exception:
            return [TextContent(type="text", text=json.dumps({"nodes": 0, "edges": 0}))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main_sync():
    """Synchronous entry point for the pyproject.toml `cartographer-kg-server` script."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
