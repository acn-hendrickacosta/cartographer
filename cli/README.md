# Cartographer CLI

Persistent knowledge layer for Claude Code. Cartographer indexes your codebase into a vector database and knowledge graph, then surfaces relevant context automatically in every Claude Code session.

## Install

```bash
pipx install --editable ".[embeddings,mcp]"
```

Or for a shared team install, have each developer run:

```bash
pipx install "git+https://<host>/<org>/cartographer.git#subdirectory=cli[embeddings,mcp]"
```

## Quickstart

```bash
# 1. Initialize a project (run once per project)
cd /your/project
cartographer init

# 2. Index the codebase
cartographer seed .

# 3. Start the MCP servers (run once per machine, keeps running)
cartographer serve

# 4. Open Claude Code in this project — it will use the index automatically
```

After `cartographer init`, two MCP server entries are written to `.mcp.json`. Add them to Claude Code at User scope via **Settings → MCP Servers → Add** using the URLs from `.mcp.json`.

---

## Commands

### `cartographer init`

Scaffolds the project: writes `CLAUDE.md` (Cartographer section), provisions the local index (LanceDB + Kuzu), applies the cross-stack standards baseline, registers the project.

```bash
cartographer init                        # in the project root
cartographer init --stacks python,react  # with language-specific standards packs
cartographer init --topology central     # for shared team index (Phase 2)
```

Idempotent — safe to re-run after updating Cartographer.

---

### `cartographer serve`

Starts both MCP servers as persistent HTTP processes on localhost. Must be running before Claude Code sessions start.

```bash
cartographer serve                        # default: VDB on :4010, KG on :4011
cartographer serve --vdb-port 4020 --kg-port 4021
```

The servers handle all projects on the same machine — workspace is routed per-request via the `?workspace=` URL parameter written into `.mcp.json` by `cartographer init`.

**Enterprise note:** `cartographer serve` is required because enterprise Claude Code policies block stdio MCP servers. HTTP localhost servers are explicitly allowed.

---

### `cartographer seed <source>`

Indexes a file or directory into the local VDB and KG.

```bash
cartographer seed .                 # index the whole project
cartographer seed src/              # index a subdirectory
cartographer seed docs/spec.md      # index a single file
cartographer seed . --enrich        # add LLM-extracted semantic relationships (slower)
```

**Without `--enrich`** (default): uses the AST parser layer to extract structural edges — `calls`, `imports`, `extends`, `defines`. Fast, no extra dependencies, works offline.

**With `--enrich`**: additionally calls the local `claude` CLI to extract semantic relationships (`implements_spec`, `depends_on`, etc.) from spec and doc files. Code files are skipped for enrichment — AST already covers them. Requires `claude` on PATH. Expect ~30–60s per spec/doc file.

Re-run seed after significant code changes. For CI, use `--diff` (Phase 4).

---

### `cartographer doctor`

Validates the installation: config integrity, local index accessibility, MCP server reachability, parser availability.

```bash
cartographer doctor
```

---

### `cartographer detect`

Read-only report of what `cartographer init` would create or merge in the current directory. Safe to run before init.

```bash
cartographer detect
```

---

### `cartographer promote`

In local topology: no-op. In central topology (Phase 2): promotes the local index to the shared global index so teammates can see your work.

```bash
cartographer promote
cartographer promote --full      # re-promote all artifacts, not just changed ones
cartographer promote --dry-run   # report what would be promoted, write nothing
```

---

## MCP tools

Once `cartographer serve` is running and the servers are registered in Claude Code, these tools are available in every session:

### VDB tools (port 4010)

| Tool | What it does |
|---|---|
| `vdb_search(query, workspace)` | Semantic search — find files, specs, and docs relevant to a concept or task |
| `vdb_stats(workspace)` | Chunk counts per artifact type — confirms the index is populated |

### KG tools (port 4011)

| Tool | What it does |
|---|---|
| `kg_query(cypher, workspace)` | Execute a Cypher query against the knowledge graph |
| `kg_neighbors(node_id, workspace, depth)` | Get neighboring nodes at a given traversal depth |
| `kg_stats(workspace)` | Node and edge counts |

**Always pass `workspace`** — the server is shared across projects and cannot infer it.

### Knowledge graph edge types

| Edge type | Source | Meaning |
|---|---|---|
| `calls` | AST | Function A calls function B |
| `imports` | AST | File A imports file B |
| `extends` | AST | Class A extends class B |
| `defines` | AST | File defines a symbol |
| `implements_spec` | Regex | File references a spec in a comment |
| `depends_on` | LLM (`--enrich`) | Semantic dependency |

Example Cypher queries:
```cypher
-- What calls _build_prompt?
MATCH (a:Artifact)-[r:RelatesTo {type: 'calls'}]->(b:Artifact)
WHERE b.attrs CONTAINS '_build_prompt' RETURN a.path LIMIT 20

-- What would break if I change BaseValidator?
MATCH (a:Artifact)-[r:RelatesTo {type: 'extends'}]->(b:Artifact)
WHERE b.attrs CONTAINS 'BaseValidator' RETURN a.path LIMIT 10
```

---

## Optional extras

| Extra | What it adds |
|---|---|
| `embeddings` | `fastembed` for semantic VDB search (required for `vdb_search`) |
| `mcp` | MCP SDK for the HTTP servers (required for `cartographer serve`) |
| `parsers-ts` | tree-sitter TypeScript/TSX grammar for AST extraction in TS projects |
| `parsers-go` | tree-sitter Go grammar |
| `parsers-rust` | tree-sitter Rust grammar |
| `parsers-all` | All tree-sitter grammars |

Python projects work out of the box — the Python parser uses stdlib `ast`, no extra install needed. For TypeScript/Go/Rust projects, install the matching grammar extra.

---

## Updating

After pulling new code:

```bash
uv pip install -e /path/to/cartographer/cli \
  --python "/path/to/pipx/venvs/cartographer/bin/python3.13" \
  --no-deps -q
```

Then restart `cartographer serve`.
