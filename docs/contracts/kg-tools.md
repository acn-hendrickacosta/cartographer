# MCP Tool Contracts: KG Server

This document defines the tool contracts for the Cartographer KG MCP server. The server ships with the plugin and is registered in `.mcp.json` at `cartographer init`. All hooks, skills, and the CLI interact with the knowledge graph exclusively through these tools.

The KG server is driver-backed. The same tool interface is served regardless of whether the underlying backend is Kuzu (local default), Neo4j, Neptune, ArangoDB, or any other supported driver. Callers do not need to know which driver is active.

---

## Common types

### Scope

```
"local" | "global"
```

`local` addresses the per-developer namespace for the current project. `global` addresses the shared central namespace and is only available when `topology.mode = "central"` is configured. A write to `global` scope from any path other than the promotion command is rejected with `SCOPE_WRITE_FORBIDDEN`.

### NodeType

```
"module" | "symbol" | "spec" | "doc"
```

### EdgeType

```
"defines" | "references" | "implements_spec" | "depends_on" | "documents" | "supersedes"
```

### Node

```json
{
  "id":         string,      // artifact identity, e.g. "proj/src/auth.py#login"
  "project_id": string,
  "scope":      Scope,
  "type":       NodeType,
  "path":       string,      // repo-relative file path
  "name":       string,      // human-readable: file name, symbol name, spec id, or heading
  "attrs":      object       // type-specific metadata; see node type table in DATA_MODEL.md
}
```

### Edge

```json
{
  "src":        string,      // artifact identity of source node
  "dst":        string,      // artifact identity of destination node
  "type":       EdgeType,
  "scope":      Scope,
  "attrs":      object       // edge-specific metadata, kept minimal
}
```

### NodeMatch

```json
{
  "node":      Node,
  "distance":  integer | null   // hop count from the query anchor; null for pattern-match results
}
```

### Error codes

| Code | Meaning |
|---|---|
| `NAMESPACE_NOT_FOUND` | The target namespace does not exist. Call `kg_ensure_namespace` first. |
| `SCOPE_WRITE_FORBIDDEN` | A write to `global` scope was attempted outside the promotion path. |
| `NODE_NOT_FOUND` | The specified `node_id` does not exist in the namespace. |
| `INVALID_EDGE_TYPE` | The `type` field is not a recognized EdgeType value. |
| `INVALID_NODE_TYPE` | The `type` field is not a recognized NodeType value. |
| `INVALID_SCOPE` | The `scope` argument is not `"local"` or `"global"`. |
| `BACKEND_UNAVAILABLE` | The underlying driver cannot reach its backend. |
| `INVALID_ARGUMENT` | A required field is missing or fails type validation. |

---

## Tools

### `kg_ensure_namespace`

Provision the KG namespace for a project and scope. Idempotent: calling it on an already-provisioned namespace is safe and returns success without modifying the namespace.

This tool is called by `cartographer init` during workspace setup. It must be called before any other KG tool for a given `(project_id, scope)` pair.

**Input**

```json
{
  "project_id": string,   // required
  "scope":      Scope     // required
}
```

**Output**

```json
{
  "namespace_name": string,   // e.g. "carto_<project_id>_local"
  "created":        boolean   // true if newly created, false if already existed
}
```

**Errors:** `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

---

### `kg_upsert_nodes`

Insert or update one or more nodes in the namespace. Keyed on `node.id`: if a node with the same `id` already exists, it is replaced in full. All nodes in a single call must belong to the same `project_id` and `scope`.

**Input**

```json
{
  "project_id": string,   // required; must match the project_id in every node
  "scope":      Scope,    // required; must match the scope in every node
  "nodes":      Node[]    // required; 1 to 500 nodes per call
}
```

**Output**

```json
{
  "upserted_count": integer,
  "inserted_count": integer,
  "updated_count":  integer
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `INVALID_NODE_TYPE`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- Maximum 500 nodes per call. Callers must batch larger sets.
- Upserting a node does not affect its edges. Edges must be managed independently via `kg_upsert_edges` and `kg_delete_edges`.

---

### `kg_upsert_edges`

Insert or update one or more edges in the namespace. An edge is uniquely identified by the combination of `(src, dst, type, scope)`. If an edge with the same composite key already exists, it is replaced in full. All edges in a single call must belong to the same `scope`.

**Input**

```json
{
  "project_id": string,   // required
  "scope":      Scope,    // required
  "edges":      Edge[]    // required; 1 to 1000 edges per call
}
```

**Output**

```json
{
  "upserted_count": integer,
  "inserted_count": integer,
  "updated_count":  integer
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `INVALID_EDGE_TYPE`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- The server does not validate that `src` and `dst` nodes exist. Edges with dangling references are permitted. This allows ingestion pipelines to write edges and nodes in separate batches without enforcing order.
- Maximum 1000 edges per call. Callers must batch larger sets.

---

### `kg_query`

Find nodes in the namespace by property filter. Returns all nodes matching the specified criteria.

**Input**

```json
{
  "project_id":  string,       // required
  "scope":       Scope,        // required
  "node_types":  NodeType[],   // optional; filter to specific node types
  "path_prefix": string,       // optional; filter to nodes whose path starts with this string
  "name_contains": string,     // optional; case-insensitive substring match on node.name
  "limit":       integer       // optional; max results to return (default 100, max 500)
}
```

**Output**

```json
{
  "nodes": NodeMatch[]   // distance is null for all results from this tool
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `INVALID_NODE_TYPE`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- All filter fields are ANDed together. An empty filter (no optional fields set) returns all nodes up to `limit`.
- For traversal-based queries, use `kg_neighbors` instead.

---

### `kg_neighbors`

Traverse the graph from an anchor node and return nodes reachable within a given number of hops. Used by the recall hooks to find artifacts related to the current working set.

**Input**

```json
{
  "project_id":   string,       // required
  "scope":        Scope,        // required
  "node_id":      string,       // required; the artifact identity of the anchor node
  "depth":        integer,      // required; max traversal depth (1 to 4)
  "edge_types":   EdgeType[],   // optional; traverse only these edge types; all types if omitted
  "node_types":   NodeType[],   // optional; return only nodes of these types; all types if omitted
  "direction":    string        // optional; "outbound", "inbound", or "any" (default "any")
}
```

**Output**

```json
{
  "anchor":    Node,
  "neighbors": NodeMatch[]   // each NodeMatch includes distance (hop count from anchor)
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `NODE_NOT_FOUND`, `INVALID_EDGE_TYPE`, `INVALID_NODE_TYPE`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- `depth` is capped at 4. Requests above 4 are rejected with `INVALID_ARGUMENT` rather than silently clamped, because deep traversals can return very large result sets on dense graphs.
- Results do not include the anchor node itself.
- If `node_id` does not exist in the namespace, `NODE_NOT_FOUND` is returned. This can happen when a hook queries for neighbors of a file that has not yet been ingested; callers should handle it gracefully by treating it as an empty result.
- For the recall hooks, the recommended depth is 2 (direct neighbors and their neighbors). This is configurable via `recall.kg_neighborhood_depth` in `cartographer.toml`.

---

### `kg_delete_nodes`

Delete nodes by their `id` values. Deleting a node also deletes all edges where the node appears as `src` or `dst`. Idempotent: deleting a node that does not exist is not an error.

**Input**

```json
{
  "project_id": string,    // required
  "scope":      Scope,     // required
  "node_ids":   string[]   // required; list of artifact identities to delete (max 500 per call)
}
```

**Output**

```json
{
  "deleted_nodes_count": integer,
  "deleted_edges_count": integer   // edges cascade-deleted with their nodes
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

---

### `kg_delete_edges`

Delete specific edges by their composite key `(src, dst, type)`. Idempotent: deleting an edge that does not exist is not an error. Does not delete the source or destination nodes.

**Input**

```json
{
  "project_id": string,                               // required
  "scope":      Scope,                                // required
  "edges": [                                          // required; list of edge keys to delete
    { "src": string, "dst": string, "type": EdgeType }
  ]
}
```

**Output**

```json
{
  "deleted_count": integer
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `INVALID_EDGE_TYPE`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

---

### `kg_namespace_stats`

Return metadata about a namespace. Used by `cartographer doctor` to verify the namespace is provisioned correctly.

**Input**

```json
{
  "project_id": string,   // required
  "scope":      Scope     // required
}
```

**Output**

```json
{
  "namespace_name":  string,
  "node_count":      integer,
  "edge_count":      integer,
  "node_type_counts": {
    "module":  integer,
    "symbol":  integer,
    "spec":    integer,
    "doc":     integer
  },
  "edge_type_counts": {
    "defines":          integer,
    "references":       integer,
    "implements_spec":  integer,
    "depends_on":       integer,
    "documents":        integer,
    "supersedes":       integer
  },
  "last_updated_at": string | null
}
```

**Errors:** `NAMESPACE_NOT_FOUND`, `INVALID_SCOPE`, `BACKEND_UNAVAILABLE`

---

## Driver implementation requirements

Any KG driver implementing this contract must satisfy the following:

1. **Idempotent upsert.** Upserting a node or edge with an existing key replaces it in full, including all `attrs` fields.
2. **Cascade delete.** Deleting a node via `kg_delete_nodes` must also delete all edges where that node appears as `src` or `dst`.
3. **Isolated namespaces per scope.** Local and global namespaces for the same project must be independent. A query to local scope must never return nodes or edges from global scope.
4. **Dangling edge tolerance.** Edges referencing non-existent nodes must be stored without error. The driver must not enforce referential integrity between edges and nodes.
5. **No cross-project leakage.** A query to `(project_id=A, scope=local)` must never return nodes or edges belonging to `project_id=B`.
6. **Depth limit enforcement.** The driver must reject `kg_neighbors` calls with `depth > 4` rather than executing them.

---

*For the VDB tool contracts, see [vdb-tools.md](vdb-tools.md). For the node and edge schemas, see [DATA_MODEL.md](../DATA_MODEL.md).*
