# Component Spec: MCP Servers

Cartographer ships two MCP servers with the plugin: one for the vector database (VDB) and one for the knowledge graph (KG). They are the exclusive interface to the state layer. All hooks, skills, and CLI commands interact with the VDB and KG through these servers.

The servers travel with the plugin. When the plugin is installed, the server definitions are merged into `.mcp.json` at `cartographer init`. Claude Code starts and manages the server processes automatically.

---

## 1. Why two servers

The VDB and KG serve different query patterns and use different underlying backends. Separating them into two servers means:

- Each server is responsible for exactly one driver abstraction.
- A team can upgrade or swap the VDB backend without touching the KG server, and vice versa.
- The two servers can be versioned and deployed independently.

For small deployments, both servers may run as processes on the developer's machine against their local (LanceDB, Kuzu) backends. For central topology, the same servers point to remote backends via the endpoints and API keys in `.cartographer.local.toml`.

---

## 2. Server definitions

These entries are written into `.mcp.json` by `cartographer init`. The `${CLAUDE_PLUGIN_ROOT}` variable is resolved by Claude Code at startup to the plugin install directory.

```json
{
  "mcpServers": {
    "cartographer-vdb": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/vdb_server.py"],
      "env": {
        "CARTO_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}",
        "CARTO_CONFIG_PATH": "${CLAUDE_PROJECT_DIR}/cartographer.toml"
      }
    },
    "cartographer-kg": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/kg_server.py"],
      "env": {
        "CARTO_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}",
        "CARTO_CONFIG_PATH": "${CLAUDE_PROJECT_DIR}/cartographer.toml"
      }
    }
  }
}
```

Secrets (API keys, endpoints) are read from `.cartographer.local.toml` and `CARTO_*` environment variables at server startup. They are never embedded in `.mcp.json`.

---

## 3. VDB server (`cartographer-vdb`)

### 3.1 Responsibilities

- Serve the VDB tool contract defined in [contracts/vdb-tools.md](../contracts/vdb-tools.md).
- Load the configured VDB driver at startup and hold the connection for the session lifetime.
- Enforce scope write protection: reject writes to `global` scope from any caller except the promotion path.
- Enforce per-call limits: chunk count (500), result count (50).

### 3.2 Startup sequence

```
Server process starts
  -> Load CARTO_CONFIG_PATH
  -> Merge .cartographer.local.toml and CARTO_* env vars
  -> Instantiate configured VDB driver (lancedb / qdrant / pgvector / opensearch / weaviate)
  -> For lancedb: open on-disk store at vdb.local_path; no network call
  -> For remote drivers: establish connection to vdb.endpoint using vdb.api_key; verify reachability
  -> Register MCP tool handlers
  -> Signal ready to Claude Code
```

If the driver fails to initialize (backend unreachable, wrong API key, path does not exist), the server exits with a non-zero code and an error message. Claude Code reports the failed server to the developer. The session proceeds without VDB tools available; hooks that depend on VDB tools will fail gracefully (see hooks spec).

### 3.3 Tools exposed

| Tool name | Contract |
|---|---|
| `vdb_ensure_collection` | [vdb-tools.md: vdb_ensure_collection](../contracts/vdb-tools.md) |
| `vdb_upsert` | [vdb-tools.md: vdb_upsert](../contracts/vdb-tools.md) |
| `vdb_query` | [vdb-tools.md: vdb_query](../contracts/vdb-tools.md) |
| `vdb_delete` | [vdb-tools.md: vdb_delete](../contracts/vdb-tools.md) |
| `vdb_collection_stats` | [vdb-tools.md: vdb_collection_stats](../contracts/vdb-tools.md) |

### 3.4 Driver interface

The server delegates all operations to a driver instance that implements the VDB driver interface defined in `cli/src/cartographer/drivers/vdb/base.py`. The driver is selected at startup based on `vdb.driver` in config. Adding a new backend requires only a new driver class; the server and its tool handlers do not change.

### 3.5 Session lifecycle

The VDB server runs for the lifetime of the Claude Code session. It does not persist state between sessions beyond what is written to the backend. On session end, the server process is terminated by Claude Code.

For the local LanceDB driver, the on-disk store persists between sessions at `vdb.local_path`. No data is lost when the server process ends.

---

## 4. KG server (`cartographer-kg`)

### 4.1 Responsibilities

- Serve the KG tool contract defined in [contracts/kg-tools.md](../contracts/kg-tools.md).
- Load the configured KG driver at startup and hold the connection for the session lifetime.
- Enforce scope write protection: reject writes to `global` scope from any caller except the promotion path.
- Enforce depth limit: reject `kg_neighbors` calls with `depth > 4`.

### 4.2 Startup sequence

```
Server process starts
  -> Load CARTO_CONFIG_PATH
  -> Merge .cartographer.local.toml and CARTO_* env vars
  -> Instantiate configured KG driver (kuzu / neo4j / neptune / arangodb)
  -> For kuzu: open on-disk store at kg.local_path; no network call
  -> For remote drivers: establish connection to kg.endpoint using kg.api_key; verify reachability
  -> Register MCP tool handlers
  -> Signal ready to Claude Code
```

Same failure behavior as the VDB server: exit non-zero if driver fails to initialize.

### 4.3 Tools exposed

| Tool name | Contract |
|---|---|
| `kg_ensure_namespace` | [kg-tools.md: kg_ensure_namespace](../contracts/kg-tools.md) |
| `kg_upsert_nodes` | [kg-tools.md: kg_upsert_nodes](../contracts/kg-tools.md) |
| `kg_upsert_edges` | [kg-tools.md: kg_upsert_edges](../contracts/kg-tools.md) |
| `kg_query` | [kg-tools.md: kg_query](../contracts/kg-tools.md) |
| `kg_neighbors` | [kg-tools.md: kg_neighbors](../contracts/kg-tools.md) |
| `kg_delete_nodes` | [kg-tools.md: kg_delete_nodes](../contracts/kg-tools.md) |
| `kg_delete_edges` | [kg-tools.md: kg_delete_edges](../contracts/kg-tools.md) |
| `kg_namespace_stats` | [kg-tools.md: kg_namespace_stats](../contracts/kg-tools.md) |

### 4.4 Driver interface

Same pattern as the VDB server. The server delegates to a driver instance implementing the KG driver interface in `cli/src/cartographer/drivers/kg/base.py`. New backends require only a new driver class.

### 4.5 Session lifecycle

Same as the VDB server. The Kuzu on-disk store persists at `kg.local_path` between sessions.

---

## 5. Scope protection

Both servers enforce the rule that only the promotion path may write to `global` scope. This is implemented as follows:

- The promotion path (`cartographer promote`) passes an internal promotion token in the tool call metadata when writing to global scope.
- The server validates the token. If the token is absent or invalid and the requested scope is `global`, the server returns `SCOPE_WRITE_FORBIDDEN`.
- The promotion token is generated at `cartographer init` and stored in `.cartographer.local.toml` (gitignored). It is not a security control against a malicious actor with filesystem access; it is a safeguard against accidental global writes from hooks or skills.

---

## 6. Tool call authorization summary

| Caller | Can write local | Can write global | Can read local | Can read global |
|---|---|---|---|---|
| Ingest flush hook | Yes | No | Yes | No |
| Preload hook | No | No | Yes | Yes (if central) |
| Retrieve hook | No | No | Yes | Yes (if central) |
| Recall skill | No | No | Yes | Yes (if central) |
| Archaeology skill | Yes | No | Yes | No |
| `cartographer promote` | No | Yes | Yes | Yes |
| `cartographer seed` | Yes | No | Yes | No |
| `cartographer doctor` | No | No | Yes | Yes (stats only) |

---

## 7. Logging and observability

Both servers log to `~/.cartographer/mcp.log` at the configured log level (`CARTO_LOG_LEVEL`). Logs include:

- Tool call name, project_id, scope, result count or upserted count, and latency.
- Driver errors with full error message.
- Startup and shutdown events.

Logs never include chunk text, embedding vectors, node content, or API keys.

---

## 8. Health check

Both servers expose a `ping` tool used by `cartographer doctor`:

**Tool: `vdb_ping` / `kg_ping`**

Input: none.

Output:
```json
{
  "status": "ok",
  "driver": "lancedb",
  "version": "0.1.0"
}
```

If the server is running but the backend is unreachable, returns:
```json
{
  "status": "error",
  "driver": "lancedb",
  "error": "<driver error message>"
}
```

---

## 9. Adding a new backend driver

To add support for a new VDB or KG backend:

1. Create a new driver class in `cli/src/cartographer/drivers/vdb/` or `cli/src/cartographer/drivers/kg/` that inherits from the base driver interface.
2. Implement all required methods defined in the base class.
3. Register the driver in the driver registry in `cli/src/cartographer/drivers/vdb/__init__.py` or the KG equivalent, keyed by the `driver` config value.
4. Add the driver's dependencies to `cli/pyproject.toml` as an optional extra (e.g. `pip install "cartographer-cli[qdrant]"`).
5. Document the driver's config requirements in `docs/CONFIGURATION.md`.
6. Add an ADR recording the decision to add the driver.

The server code does not change when a new driver is added.

---

*For the full tool contracts, see [contracts/vdb-tools.md](../contracts/vdb-tools.md) and [contracts/kg-tools.md](../contracts/kg-tools.md). For hook scripts that call these tools, see [hooks.md](hooks.md).*
