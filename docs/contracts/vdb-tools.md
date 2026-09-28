# MCP Tool Contracts: VDB Server

This document defines the tool contracts for the Cartographer VDB MCP server. The server ships with the plugin and is registered in `.mcp.json` at `cartographer init`. All hooks, skills, and the CLI interact with the VDB exclusively through these tools.

The VDB server is driver-backed. The same tool interface is served regardless of whether the underlying backend is LanceDB (local default), pgvector, Qdrant, OpenSearch, or any other supported driver. Callers do not need to know which driver is active.

---

## Common types

These types are referenced across multiple tool contracts.

### Scope

```
"local" | "global"
```

`local` addresses the per-developer collection for the current project. `global` addresses the shared central collection and is only available when `topology.mode = "central"` is configured. A write to `global` scope from any path other than the promotion command is rejected with `SCOPE_WRITE_FORBIDDEN`.

### ArtifactType

```
"code" | "spec" | "doc"
```

### Chunk

```json
{
  "id":            string,    // artifact identity + chunk ordinal, e.g. "proj/src/auth.py#login:0"
  "project_id":    string,
  "scope":         Scope,
  "artifact_type": ArtifactType,
  "path":          string,    // repo-relative file path
  "symbol":        string | null,
  "spec_id":       string | null,
  "heading":       string | null,
  "origin":        "local" | "global",
  "text":          string,
  "embedding":     number[],  // dimensionality must match the collection's configured dimensions
  "updated_at":    string     // ISO 8601 timestamp
}
```

### ScoredChunk

```json
{
  "chunk":  Chunk,
  "score":  number   // cosine similarity, range [0.0, 1.0], higher is more similar
}
```

### Error codes

| Code | Meaning |
|---|---|
| `COLLECTION_NOT_FOUND` | The target collection does not exist. Call `vdb_ensure_collection` first. |
| `SCOPE_WRITE_FORBIDDEN` | A write to `global` scope was attempted outside the promotion path. |
| `DIMENSION_MISMATCH` | The embedding vector length does not match the collection's configured dimensions. |
| `INVALID_SCOPE` | The `scope` argument is not `"local"` or `"global"`. |
| `BACKEND_UNAVAILABLE` | The underlying driver cannot reach its backend. |
| `INVALID_ARGUMENT` | A required field is missing or fails type validation. |

---

## Tools

### `vdb_ensure_collection`

Provision the VDB collection for a project and scope. Idempotent: calling it on an already-provisioned collection is safe and returns success without modifying the collection.

This tool is called by `cartographer init` during workspace setup. It must be called before any other VDB tool for a given `(project_id, scope)` pair.

**Input**

```json
{
  "project_id": string,    // required
  "scope":      Scope,     // required
  "dimensions": integer    // required; embedding vector length for this collection
}
```

**Output**

```json
{
  "collection_name": string,   // the provisioned collection name, e.g. "carto_<project_id>_local"
  "created":         boolean   // true if newly created, false if already existed
}
```

**Errors:** `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

---

### `vdb_upsert`

Insert or update one or more chunks in the collection. Keyed on `chunk.id`: if a chunk with the same `id` already exists in the collection, it is replaced in full. If it does not exist, it is inserted. All chunks in a single call must belong to the same `project_id` and `scope`.

**Input**

```json
{
  "project_id": string,    // required; must match the project_id in every chunk
  "scope":      Scope,     // required; must match the scope in every chunk
  "chunks":     Chunk[]    // required; 1 to 500 chunks per call
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

**Errors:** `COLLECTION_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `DIMENSION_MISMATCH`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- Maximum 500 chunks per call. Callers must batch larger sets.
- `SCOPE_WRITE_FORBIDDEN` is returned if `scope = "global"` and the call does not originate from the promotion path. The promotion path authenticates itself by passing an internal promotion token; all other callers are blocked from writing to global scope.
- `updated_at` in each chunk should be set by the caller to the current timestamp. The server does not set it.

---

### `vdb_query`

Perform a semantic similarity search over the collection. Returns the top-k chunks most similar to the query text, scored by cosine similarity.

**Input**

```json
{
  "project_id":     string,          // required
  "scope":          Scope,           // required
  "text":           string,          // required; the query string to embed and search against
  "k":              integer,         // required; number of results to return (max 50)
  "artifact_types": ArtifactType[],  // optional; filter to specific artifact types
  "min_score":      number           // optional; exclude results below this cosine similarity threshold
}
```

**Output**

```json
{
  "results": ScoredChunk[],   // ordered by score descending
  "query_id": string          // opaque identifier for this query, for logging
}
```

**Errors:** `COLLECTION_NOT_FOUND`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

**Notes:**
- If the collection exists but is empty, returns an empty `results` array, not an error.
- `k` is capped at 50. Requests above 50 are silently clamped.
- `artifact_types` filter is applied after vector search, not before. The server retrieves `k` candidates and then filters; the returned count may be less than `k` if the filter removes results.
- For local-then-global read order, the caller (hook or skill) issues two separate `vdb_query` calls and merges the results. The server does not perform cross-scope queries.

---

### `vdb_delete`

Delete chunks by their `id` values. Idempotent: deleting an `id` that does not exist is not an error.

**Input**

```json
{
  "project_id": string,    // required
  "scope":      Scope,     // required
  "ids":        string[]   // required; list of chunk ids to delete (max 1000 per call)
}
```

**Output**

```json
{
  "deleted_count": integer   // number of chunks that existed and were deleted
}
```

**Errors:** `COLLECTION_NOT_FOUND`, `SCOPE_WRITE_FORBIDDEN`, `INVALID_SCOPE`, `INVALID_ARGUMENT`, `BACKEND_UNAVAILABLE`

---

### `vdb_collection_stats`

Return metadata about a collection. Used by `cartographer doctor` to verify the collection is provisioned correctly.

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
  "collection_name": string,
  "chunk_count":     integer,
  "dimensions":      integer,
  "size_bytes":      integer,
  "last_updated_at": string | null   // ISO 8601; null if collection is empty
}
```

**Errors:** `COLLECTION_NOT_FOUND`, `INVALID_SCOPE`, `BACKEND_UNAVAILABLE`

---

## Driver implementation requirements

Any VDB driver implementing this contract must satisfy the following:

1. **Idempotent upsert.** Upserting a chunk with an existing `id` replaces it in full, including the embedding vector and all metadata fields.
2. **Isolated collections per scope.** Local and global collections for the same project must be independent. A query to local scope must never return results from global scope, and vice versa.
3. **Consistent dimensionality.** All chunks in a collection share the same vector dimensionality. The driver rejects upserts with mismatched dimensions rather than silently truncating or padding.
4. **Atomic batch upserts.** A `vdb_upsert` call either commits all chunks or none. Partial writes on failure are not acceptable.
5. **No cross-project leakage.** A query to `(project_id=A, scope=local)` must never return chunks belonging to `project_id=B`.

---

*For the KG tool contracts, see [kg-tools.md](kg-tools.md). For the data schemas these tools operate on, see [DATA_MODEL.md](../DATA_MODEL.md).*
