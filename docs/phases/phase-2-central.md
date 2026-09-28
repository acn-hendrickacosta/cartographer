# Phase 2: Configurable Central

## Goal

A second developer joins a project. After a branch merges to main, they see the first developer's merged knowledge in their session through the global index. Switching a project from local to central topology is a configuration change, not a code change.

**Entry condition:** Phase 1 is complete and stable. All Phase 1 exit criteria have been demonstrated. The recall loop works reliably in local topology before central topology is added.

---

## References

| Document | What to read |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Sections 4-7: two-pronged model, deployment topologies, AWS reference deployment |
| [APPLICATION_ARCHITECTURE.md](../APPLICATION_ARCHITECTURE.md) | Part 1: promote command flow; hook flows for central topology |
| [DATA_MODEL.md](../DATA_MODEL.md) | Sections 5-6: scoping rules, promotion mechanics, promotion trigger options |
| [CONFIGURATION.md](../CONFIGURATION.md) | Central topology config: `topology.mode`, `vdb.endpoint`, `kg.endpoint`, API keys in local override |
| [SECURITY_AND_ISOLATION.md](../SECURITY_AND_ISOLATION.md) | Sections 2-3: tenant isolation in central topology, egress to central backend |
| [components/cli.md](../components/cli.md) | `promote` command spec; `doctor` central checks |
| [components/mcp-servers.md](../components/mcp-servers.md) | Central backend driver loading; scope write protection; promotion token |
| [contracts/vdb-tools.md](../contracts/vdb-tools.md) | Global scope operations; SCOPE_WRITE_FORBIDDEN error |
| [contracts/kg-tools.md](../contracts/kg-tools.md) | Global scope operations; SCOPE_WRITE_FORBIDDEN error |
| [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) | OQ-08 through OQ-10 are Phase 2 blockers (Standards Registry -- separate track, but OQ-10 affects CLI behavior) |
| [adr/0006-driver-interface-for-backends.md](../adr/0006-driver-interface-for-backends.md) | Why the driver interface enables cloud-agnostic central backends |

---

## Scope

### In scope

| Component | What ships |
|---|---|
| Central VDB driver | pgvector (PostgreSQL + pgvector extension). Cloud-agnostic; runs on any PostgreSQL host. |
| Central KG driver | Neo4j. Cloud-agnostic; runs locally via Docker, on Neo4j Aura, or any self-hosted instance. |
| Promotion pipeline | `cartographer promote` writes to global scope; idempotent upserts keyed on artifact identity |
| Promotion triggers | CI step documented and templated; post-merge hook script provided; manual command working |
| Global index read order | Local-first in recall hooks and recall skill; results tagged by origin (local/global) |
| Central backend auth | Per-developer connection details in `.cartographer.local.toml` or env vars; provisioned by admin |
| `doctor` central checks | pgvector reachable; Neo4j reachable; credentials accepted |
| Scope write protection | Promotion token enforced in both MCP servers; global write rejected outside promotion |
| Two-developer walkthrough | Documented runbook for setting up and verifying two developers sharing a global index |

### Explicitly out of scope

- Deletion and rename reconciliation across the promotion boundary (Phase 3)
- Rebase and history-rewrite handling (Phase 3)
- Conflict resolution when local and global disagree (Phase 3)
- Standards Registry and web app (independent track)
- Binary document extraction (deferred, see OQ-07)

---

## Component breakdown

### 1. Central VDB driver

**pgvector driver** (`cli/src/cartographer/indexing/vdb_pgvector.py`):
- Implement the same interface as the local LanceDB driver
- Connection: `psycopg2` using host, port, user, password, database from `.cartographer.local.toml` or env vars
- Collection mapping: each `carto_<project_id>_global` maps to a pgvector table with a `vector(<dim>)` column
- `ensure_collection`: `CREATE TABLE IF NOT EXISTS` with vector column of correct dimensionality
- `upsert`: `INSERT ... ON CONFLICT (id) DO UPDATE` keyed on chunk `id`
- `query`: `SELECT ... ORDER BY embedding <=> %s LIMIT %s` with optional SQL filter
- `delete`: `DELETE WHERE id = ANY(%s)`
- `collection_stats`: `SELECT artifact_type, COUNT(*) FROM ... GROUP BY artifact_type`

**ADR required:** One ADR for the pgvector driver (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

**Reference:** [contracts/vdb-tools.md: Driver implementation requirements](../contracts/vdb-tools.md)

---

### 2. Central KG driver

**Neo4j driver** (`cli/src/cartographer/indexing/kg_neo4j.py`):
- Implement the same interface as the local Kuzu driver
- Connection: `neo4j` Python driver using the Bolt URI, user, and password from `.cartographer.local.toml` or env vars
- Namespace mapping: each `carto_<project_id>_global` maps to a labeled subgraph (node label prefix + relationship type prefix)
- All operations implemented using Cypher queries
- `ensure_namespace`: create index constraints if absent; idempotent
- `upsert_nodes`: `MERGE (n:Artifact {id: $id}) ON CREATE SET ... ON MATCH SET ...`
- `upsert_edges`: `MATCH (s), (d) MERGE (s)-[r:RelatesTo {type: $type}]->(d) ON CREATE SET ... ON MATCH SET ...`
- `query`: pass-through Cypher execution with params
- `neighbors`: multi-hop Cypher traversal with configurable depth (max 4)
- `delete_nodes`: `MATCH (n {id: $id}) DETACH DELETE n` (cascade-deletes attached edges)
- `delete_edges`: `MATCH (s)-[r:RelatesTo {type: $type}]->(d) DELETE r`
- `namespace_stats`: `MATCH (n:Artifact) RETURN count(*)` + edge count query

**ADR required:** One ADR for the Neo4j driver.

**Reference:** [contracts/kg-tools.md: Driver implementation requirements](../contracts/kg-tools.md)

---

### 3. Promotion pipeline

**`cartographer promote` command** (update existing no-op in Phase 1):
- Load config; validate `topology.mode = "central"`; validate central backend reachability
- Determine promotion scope: artifacts changed since `last_promoted_at` (default) or all artifacts (`--full`)
- Re-ingest each artifact against global scope using the same ingestion pipeline as Phase 1
- Promotion token: generate at `cartographer init` (central topology), store in `.cartographer.local.toml`; pass in MCP tool call metadata for scope write authorization
- Update `last_promoted_at` in registry on success
- `--dry-run` flag: report artifact list and exit without writing

**Scope write protection in MCP servers** (add to both Phase 1 servers):
- Both VDB and KG servers validate a promotion token in tool call metadata before allowing any write to `global` scope
- Token generated at `cartographer init` when `topology.mode = "central"`, stored in `.cartographer.local.toml`
- Any write to `global` scope without a valid token returns `SCOPE_WRITE_FORBIDDEN`

**Reference:** [components/cli.md: cartographer promote](../components/cli.md), [DATA_MODEL.md: Promotion mechanics](../DATA_MODEL.md)

---

### 4. Global index read order

**Recall hooks update** (update Phase 1 hook scripts):

`preload.py`:
- After local VDB + KG queries: if `topology.mode = "central"`, run the same queries against global scope
- Merge results: local results shadow global results for the same artifact identity
- Tag each result with origin: `local` or `global`
- Format merged results within `recall.preload_budget_tokens`

`retrieve.py`:
- Same pattern as preload: local first, then global if central, then merge and tag

**Recall skill update** (`skills/recall/SKILL.md`):
- Update steps to include global scope query when central topology is configured
- Merge and tag results by origin before presenting

---

### 5. Configuration additions

New config fields required for central topology (add to `cartographer.toml` reference and `cartographer.example.toml`):

```toml
[vdb]
# endpoint and api_key go in .cartographer.local.toml

[kg]
# endpoint and api_key go in .cartographer.local.toml
```

No new fields in the committed `cartographer.toml`. All central backend connection details stay in the gitignored local override.

---

### 6. `doctor` central checks

Add to the `cartographer doctor` command:
- `vdb.endpoint` reachable (HTTP health check or collection list)
- `vdb` API key accepted (attempt an `ensure_collection` with a test project id)
- `kg.endpoint` reachable
- `kg` API key accepted (attempt an `ensure_namespace` with a test project id)
- Promotion token is present in `.cartographer.local.toml` (for central topology)

---

## Build order

```
1. Resolve Phase 2 open questions (endpoints, auth model for chosen central backends)
2. pgvector VDB driver + integration tests
3. Neo4j KG driver + integration tests
4. Promotion token generation at init (update init command)
5. Scope write protection in both MCP servers (promotion token validation)
6. cartographer promote command (replaces Phase 1 no-op)
7. Global index read order in preload and retrieve hooks
8. doctor central checks
9. Qdrant VDB driver (second driver, parallel with steps 4-8)
10. Neptune KG driver (second driver, parallel with steps 4-8)
11. ADRs for each new driver
12. Two-developer walkthrough runbook
```

---

## Open questions resolved

| Question | Decision |
|---|---|
| Central VDB driver | pgvector. Cloud-agnostic, runs on any PostgreSQL. No AWS dependency. |
| Central KG driver | Neo4j. Cloud-agnostic, runs locally via Docker or on Neo4j Aura. Neptune rejected -- AWS-only. |
| Promotion token | Random secret generated at `cartographer init` (central topology), stored in `.cartographer.local.toml`. |
| Central backend provisioning | Admin-managed. Admin provisions once (pgvector database + Neo4j instance), shares connection details with the team. Developers add details to their gitignored `.cartographer.local.toml`. |

---

## Exit criteria

All criteria must be demonstrated with two real developer machines (or two separate environments) and a real central backend.

| # | Criterion | How to verify |
|---|---|---|
| 1 | Developer A initializes a project with `topology.mode = "central"` | Run `cartographer init` with central config; confirm doctor passes |
| 2 | `cartographer promote` runs without error and writes to the global index | Run `cartographer promote`; check `vdb_collection_stats` and `kg_namespace_stats` for global scope; counts must be non-zero |
| 3 | Promotion is idempotent | Run `cartographer promote` twice; stats counts must be identical after both runs |
| 4 | Developer B initializes the same project on a separate machine with their own API key | `cartographer doctor` passes on Developer B's machine; global scope is reachable |
| 5 | After Developer A promotes, Developer B's session preloads from both local and global scope | Open session as Developer B; observe origin tags (`local`, `global`) in the preload context block |
| 6 | A VDB query returns local-first results with global fallback; results are tagged by origin | Run `cartographer recall --scope both`; verify both origin tags appear |
| 7 | Local results shadow global results for the same artifact identity | Promote an artifact; edit it locally without promoting; run recall; verify the local version is returned, not the promoted version |
| 8 | Tenant isolation holds in central topology | Two projects with different tenants; confirm cross-tenant recall is blocked |
| 9 | Scope write protection works | Attempt to write to global scope from a hook (not the promote path); confirm `SCOPE_WRITE_FORBIDDEN` is returned |
| 10 | `cartographer doctor` passes all central checks on both machines | Run doctor on both Developer A and Developer B machines; exit code `0` |

---

## Test approach

### Unit tests (additions to Phase 1 suite)

| Area | What to test |
|---|---|
| Promotion token validation | Valid token allows global write; absent or invalid token returns SCOPE_WRITE_FORBIDDEN |
| Global scope read order | Local results returned first; local shadows global for same artifact identity; origin tags correct |
| Promote command: scope determination | Changed-since logic using `last_promoted_at`; `--full` flag overrides to all artifacts |
| Promote command: `--dry-run` | Reports artifact list, writes nothing |

### Integration tests

Each central driver gets its own integration test suite. Tests require a running instance of the backend (pgvector, Neo4j, etc.). Use Docker Compose for CI.

**pgvector driver tests:**
- `ensure_collection` creates table with correct vector dimensionality
- `upsert` inserts and updates by chunk `id`
- `query` returns correct top-k results ordered by cosine similarity
- `delete` removes by id list; deleting non-existent ids is not an error
- Dimension mismatch returns `DIMENSION_MISMATCH`

**Neo4j driver tests:**
- `ensure_namespace` creates labeled subgraph or database
- `upsert_nodes` inserts and updates by node `id`
- `upsert_edges` with dangling references (src or dst not yet in graph) succeeds
- `neighbors` at depth 1, 2; edge type filter; direction filter
- `delete_nodes` cascade-deletes attached edges
- Depth > 4 returns `INVALID_ARGUMENT`

**Promotion integration test:**
- Ingest artifacts to local scope; run `cartographer promote`; verify artifacts appear in global scope with correct metadata
- Run `cartographer promote` again (idempotent); verify counts unchanged

### End-to-end acceptance test (two-developer walkthrough)

Run this as a documented runbook. Requires two machines or two isolated environments.

```
Setup:
  - Provision a central pgvector instance and Neo4j instance
  - Issue two API keys: one for Dev A, one for Dev B

Dev A:
  1. cartographer init --stack python --yes  (topology.mode = central in toml)
  2. Configure .cartographer.local.toml with central endpoints and Dev A API key
  3. cartographer doctor  (must pass all central checks)
  4. Add a Python module; work in a Claude Code session for 10 minutes
  5. Merge the branch to main (or simulate by running cartographer promote)
  6. Confirm promote completes; note global scope chunk and node counts

Dev B (separate machine, same repo):
  1. Clone the repo
  2. cartographer init --stack python --yes
  3. Configure .cartographer.local.toml with central endpoints and Dev B API key
  4. cartographer doctor  (must pass)
  5. Open a Claude Code session
  6. Observe preload context: must include artifacts promoted by Dev A, tagged origin: global
  7. Ask about the code Dev A wrote without mentioning it explicitly
  8. Verify Claude answers using the globally recalled knowledge
```

Pass criterion: step B.8 succeeds. Dev B's session recalls Dev A's work via the global index.

---

*For phase exit criteria summary, see [ROADMAP.md](../ROADMAP.md). For Phase 1 foundation, see [phase-1-mvp-local.md](phase-1-mvp-local.md).*
