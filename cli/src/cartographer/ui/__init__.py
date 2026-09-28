"""Local knowledge browser: `cartographer ui` command.

Starts a FastAPI server at localhost:7341 with four views:
  - /search  — semantic search over the local VDB
  - /graph   — KG node and edge explorer (D3 for rendering)
  - /registry — registered projects on this machine
  - /stats   — chunk, node, edge counts per artifact type
"""
