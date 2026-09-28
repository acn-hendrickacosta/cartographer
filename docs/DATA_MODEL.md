# Cartographer: Data Architecture and Data Model

This document describes the three stores that make up the Cartographer knowledge layer: the vector database (VDB), the knowledge graph (KG), and the project registry. It covers schemas, artifact identity, scoping rules, promotion mechanics, and the gaps that are explicitly deferred.

---

## 1. Overview

Cartographer maintains three logical stores per deployment. Each has a distinct purpose and a distinct query pattern.

| Store | Purpose | Default backend | Query pattern |
|---|---|---|---|
| VDB | Semantic recall: find relevant chunks of code, specs, or docs given a natural-language query | LanceDB (embedded) | Approximate nearest-neighbor over embeddings |
| KG | Structural recall: find artifacts by relationship, navigate dependencies, anchor specs to code | Kuzu (embedded) | Graph traversal, pattern match |
| Registry | Project inventory: track which projects exist, their topology, and their index locations | SQLite (local file) | Key-value and filter lookup |

The VDB and KG are complementary. The VDB finds relevant content when the query is fuzzy ("how did we handle auth in the billing service?"). The KG finds related artifacts when the relationship is known ("what symbols implement this spec node?", "what does this module depend on?"). Recall hooks query both and merge the results before injecting them into context.

All three stores operate under a scope: `local` or `global`. Local scope is always present. Global scope is only present when a central backend is configured.

---

## 2. Artifact identity

Artifact identity is the stable key used across both the VDB and the KG. It must survive file renames and squash merges without corrupting the global index.

| Artifact type | Identity key |
|---|---|
| Code symbol | `<project_id>/<relative_file_path>#<symbol_name>` |
| Code file (no symbol) | `<project_id>/<relative_file_path>` |
| Spec | `<project_id>/spec/<spec_id>` where `spec_id` is the spec's declared identifier or, if absent, its relative path |
| Documentation file | `<project_id>/doc/<relative_file_path>` |
| Documentation section | `<project_id>/doc/<relative_file_path>#<heading_slug>` |

Rules:
- Identity is derived from the artifact's logical location, not from a git commit SHA or an inode.
- All upserts (VDB and KG) are keyed on identity. Writing the same artifact twice is idempotent.
- Promotion from local to global is an idempotent upsert keyed on identity. A squash merge that collapses many commits into one does not produce duplicate or corrupt entries.
- Renames and deletions across the promotion boundary are a known gap. See Section 7.

---

## 3. Vector database (VDB)

### 3.1 Collection structure

One logical collection per project, split by scope. Each scope is either a separate collection or a filtered partition, depending on the backend driver.

| Collection name pattern | Scope | Contents |
|---|---|---|
| `carto_<project_id>_local` | local | Working state, including unmerged changes. Private to the developer's machine. |
| `carto_<project_id>_global` | global | Merged canonical state. Present only when central topology is configured. |

### 3.2 Chunk record schema

Every stored chunk carries these fields.

| Field | Type | Description |
|---|---|---|
| `id` | string | Artifact identity + chunk ordinal, e.g. `proj/src/auth.py#login:0`. Unique within a collection. |
| `project_id` | string | Stable project identifier, set at `cartographer init`. |
| `scope` | enum | `local` or `global`. |
| `artifact_type` | enum | `code`, `spec`, or `doc`. |
| `path` | string | Repo-relative file path of the source artifact. |
| `symbol` | string or null | Symbol name within the file (function, class, method). Null for file-level and doc chunks. |
| `spec_id` | string or null | Spec identifier if the chunk belongs to a spec artifact. Null otherwise. |
| `heading` | string or null | Section heading slug for doc chunks split by heading. Null for code and spec chunks. |
| `origin` | enum | `local` or `global`. Tags where the chunk was last written. Used in recall to attribute results. |
| `text` | string | The raw text of the chunk, as embedded. |
| `embedding` | vector | The embedding vector. Dimensionality set by the configured embedder. |
| `updated_at` | timestamp | When this chunk was last upserted. |

### 3.3 Chunking strategy

Chunking strategy is intentionally left to the ingestion pipeline implementation, but the following constraints apply:

- Code: chunk at the symbol boundary where possible (function, class, method). Fall back to fixed-size sliding window with overlap for files with no parseable symbol structure.
- Specs: chunk at the section or requirement boundary. Preserve the spec's declared identifier in `spec_id`.
- Documentation (plain text: .md, .rst, .txt, .adoc): chunk at the heading boundary first. Fall back to fixed-size sliding window with overlap for sections that exceed the chunk size limit.
- Documentation (binary: .docx, .pptx, .pdf): text is extracted first by invoking Claude (local, via the MCP tool interface already in the session) before chunking. Claude extracts section headings, body text, table content, and -- for .pptx -- slide titles and speaker notes. The extracted text is then chunked by the same heading-boundary strategy as plain-text docs. No external model or API is used for this step.
- Chunk size limit and overlap are configurable. Defaults are defined in `cartographer.example.toml`.

### 3.4 Read order during recall

When a central topology is configured, the recall hooks query both scopes and merge the results before injecting them into context.

```
1. Query local scope   -> results tagged origin: local
2. Query global scope  -> results tagged origin: global
3. Merge by relevance score, deduplicate by artifact identity
4. Tag each result with its origin in the injected context
```

Local results shadow global results for the same artifact identity. This ensures that unmerged working state takes precedence over the last-promoted version of the same artifact.

---

## 4. Knowledge graph (KG)

### 4.1 Namespace structure

One logical namespace per project, split by scope. Namespaces are isolated: no edge crosses a namespace boundary.

| Namespace pattern | Scope |
|---|---|
| `carto_<project_id>_local` | local |
| `carto_<project_id>_global` | global |

### 4.2 Node schema

| Field | Type | Description |
|---|---|---|
| `id` | string | Artifact identity. Same key as the VDB. |
| `project_id` | string | Stable project identifier. |
| `scope` | enum | `local` or `global`. |
| `type` | enum | `module`, `symbol`, `spec`, `doc`. See node type table below. |
| `path` | string | Repo-relative file path. |
| `name` | string | Human-readable name: file name, symbol name, spec id, or doc heading. |
| `attrs` | map | Type-specific metadata. See node type table. |

**Node types and their `attrs`:**

| Node type | Represents | Key attrs |
|---|---|---|
| `module` | A code file or package | `language`, `package` |
| `symbol` | A function, class, or method within a file | `kind` (function/class/method), `signature` |
| `spec` | A specification artifact or a section within one | `spec_id`, `status` (draft/approved/superseded) |
| `doc` | A documentation file or a section within one | `doc_type` (readme/adr/runbook/wiki/other), `heading` |

Keep `attrs` small. Add a key only when a recall query needs it. Resist modeling everything.

### 4.3 Edge schema

| Field | Type | Description |
|---|---|---|
| `src` | string | Artifact identity of the source node. |
| `dst` | string | Artifact identity of the destination node. |
| `type` | enum | Edge type. See edge type table below. |
| `scope` | enum | `local` or `global`. |
| `attrs` | map | Edge-specific metadata, kept minimal. |

**Edge types:**

| Edge type | Meaning | Example |
|---|---|---|
| `defines` | A module defines a symbol | `src/auth.py` -> `login()` |
| `references` | A symbol or file references another | `billing.py#charge()` -> `auth.py#login()` |
| `implements_spec` | A code symbol or module implements a spec requirement | `auth.py#login()` -> `spec/AUTH-001` |
| `depends_on` | A module or package depends on another | `billing/` -> `auth/` |
| `documents` | A doc artifact describes a code or spec artifact | `docs/auth.md` -> `spec/AUTH-001` |
| `supersedes` | A spec or doc version supersedes an earlier one | `spec/AUTH-002` -> `spec/AUTH-001` |

Add a new edge type only when a recall query pattern requires it. Undirected relationships are modeled as two directed edges.

### 4.4 Graph queries used in recall

The recall hooks issue two query patterns against the KG:

| Pattern | When used | Example |
|---|---|---|
| Neighborhood lookup | Find artifacts related to the files in the current working set | Given `src/auth.py` is dirty, return its neighbors at depth 1-2 |
| Spec anchor lookup | Find code that implements a given spec node | Given `spec/AUTH-001`, return all `implements_spec` neighbors |
| Doc lookup | Find documentation describing a code or spec artifact | Given `auth.py#login()`, return all `documents` edges into doc nodes |

---

## 5. Registry

The registry is a per-machine index of projects a developer has initialized. It is used by the recall skill to locate the right index for cross-project queries and to enforce tenant isolation.

### 5.1 Project record schema

| Field | Type | Description |
|---|---|---|
| `project_id` | string | Stable identifier, generated at `cartographer init`. |
| `name` | string | Human-readable project name, derived from the root directory name or set explicitly. |
| `root_path` | string | Absolute path to the project root on this machine. |
| `topology` | enum | `local` or `central`. |
| `tenant` | string | Tenant or client identifier. Cross-project recall never crosses a tenant boundary. |
| `central_endpoint` | string or null | Base URL of the central backend. Null in local topology. |
| `active_stacks` | list of strings | Stack packs applied at init or via `stack add`. |
| `created_at` | timestamp | When `cartographer init` first ran for this project on this machine. |
| `last_indexed_at` | timestamp | When the last ingestion flush completed. |

### 5.2 Registry location

In local-only topology, the registry is a single SQLite file stored per user, outside any project directory, so it persists across project checkouts and machine reboots.

Default path: `~/.cartographer/registry.db`

This path is configurable. See `cartographer.example.toml`.

---

## 6. Scoping and promotion

### 6.1 Scope rules

| Rule | Detail |
|---|---|
| Local scope is always present | Even when central topology is configured, every developer has a local index. Local is never absent. |
| Global scope requires central topology | Global scope does not exist in local-only deployments. Queries against global scope are a no-op and return empty when no central backend is configured. |
| Unmerged state stays local | The ingestion hook always writes to local scope. Writing to global scope is only permitted via the promotion path. |
| Read local first | During recall, local scope is queried first. Local results shadow global results for the same artifact identity. |

### 6.2 Promotion mechanics

Promotion moves artifacts from local scope to global scope after a branch merges to main. It is not live sync.

```
Promotion trigger fires (CI step, post-merge hook, or cartographer promote)
  -> Identify artifacts changed in the merged branch (by artifact identity)
  -> For each artifact:
       VDB: upsert chunk(s) to global scope, keyed by id
       KG:  upsert node(s) and edge(s) to global scope, keyed by id
  -> Record last_promoted_at in the registry
```

Promotion is idempotent. Running it twice produces the same global state. This property holds because all upserts are keyed on artifact identity, not on commit SHA.

### 6.3 Promotion trigger options

| Trigger | When to use |
|---|---|
| CI step on merge to main | Preferred for teams using a CI pipeline. Reliable and automatic. |
| Git post-merge hook | Useful for local-only teams or when CI is not available. Runs on the developer's machine after `git merge`. |
| `cartographer promote` (manual) | Fallback for debugging or one-off situations. Not recommended as the primary trigger. |

The chosen trigger is set in `cartographer.toml`. See `docs/CONFIGURATION.md`.

---

## 7. Known gaps and deferred concerns

These are documented gaps in the current data model. They must not be closed silently. Each requires a design decision before implementation.

| Gap | Impact | Deferred to |
|---|---|---|
| Deletions across the promotion boundary | If a file or symbol is deleted locally and the branch merges, the global index retains the stale node and chunks indefinitely. No tombstone protocol exists yet. | Phase 3 |
| Renames across the promotion boundary | A renamed file produces a new artifact identity. The old identity's node and chunks remain in the global index. Deduplication requires a rename-tracking protocol. | Phase 3 |
| Rebase and history-rewrite handling | Artifact identity does not depend on commit SHA, so rebases are safe for the data model. However, a force-push that removes commits does not remove the corresponding artifacts from the global index. | Phase 3 |
| Conflict resolution when local and global disagree | If a developer's local version of an artifact diverges significantly from the global version (e.g., a spec is in draft locally but approved globally), there is no merge or conflict policy. The local result shadows the global during reads, which may not always be correct. | Phase 3 |
| Registry sync across machines | The registry is per-machine. A developer using two machines has two independent registries. No sync mechanism exists. | Not scheduled |

---

*For configuration of backend drivers and chunk size limits, see [CONFIGURATION.md](CONFIGURATION.md). For the driver operation contracts, see [contracts/vdb-tools.md](contracts/vdb-tools.md) and [contracts/kg-tools.md](contracts/kg-tools.md).*
