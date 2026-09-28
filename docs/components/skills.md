# Component Spec: Skills

Skills are the model-invoked layer of Cartographer. They handle deliberate, one-time, or judgment-heavy operations that must not be always-on. Cartographer ships two skills with the plugin: `archaeology` and `recall`.

The rule governing whether something belongs in a skill versus a hook is stated in [hooks.md](hooks.md). In short: if it must happen on every turn or every session, it is a hook. If it requires deliberate invocation or human judgment, it is a skill.

---

## 1. Skill: `archaeology`

### 1.1 Purpose

Bootstrap the knowledge base from an existing codebase. Walk the repository, extract artifacts and relationships into the KG, chunk and embed into the VDB, and infer implicit specs where possible. Invoked once, deliberately, typically when a developer first initializes Cartographer on an existing project.

This skill handles the cold-start problem: a project that existed before Cartographer was installed has no knowledge in the index. Archaeology reads the full repo and populates the index in one pass, after which the ingest hooks maintain it incrementally.

### 1.2 Invocation

```
/archaeology
```

Or via natural language: "run archaeology on this repo", "bootstrap the knowledge base", "index the codebase".

The skill may also be invoked with a scope:

```
/archaeology --path src/
/archaeology --path docs/
```

To index only a subdirectory.

### 1.3 Inputs

| Input | Source | Description |
|---|---|---|
| Repository root | `$CLAUDE_PROJECT_DIR` | The project root to traverse |
| Config | `cartographer.toml` | Driver selection, chunk size, exclude patterns, spec detection patterns |
| Scope path | Optional argument | Subdirectory to limit traversal to |

### 1.4 Process

```
1. Load config from cartographer.toml
2. Verify local VDB collection and KG namespace exist (call vdb_collection_stats and kg_namespace_stats)
   If either does not exist: instruct the user to run cartographer init first, stop
3. Walk the repository from the project root (or --path if given)
   Apply ingestion.exclude_patterns to skip irrelevant directories and files
4. Classify each file by artifact type:
   Spec:  matches ingestion.spec_patterns (see OQ-03)
   Doc:   matches ingestion.doc_watch_patterns or doc file extension
   Code:  everything else that is a text file
5. For each file, in order: specs first, then code, then docs
   a. Extract text:
      Plain text (code, markdown, rst, txt, adoc): read directly
      Binary (docx, pptx, pdf): invoke Claude to extract structured text
   b. Chunk extracted text by artifact type:
      Code:  at symbol boundaries; fall back to sliding window
      Spec:  at section or requirement boundaries
      Doc:   at heading boundaries; fall back to sliding window
   c. Embed each chunk using the configured embedder driver
   d. Extract KG nodes and edges:
      Code files:   module node; symbol nodes for each function/class/method; defines edges
      Spec files:   spec nodes per section; spec_id from declared identifier or path
      Doc files:    doc nodes per heading; documents edges to any referenced code or spec ids
      Cross-file:   references edges inferred from import statements and explicit citations
      Implements:   implements_spec edges inferred where a symbol name or docstring
                    references a spec identifier
   e. vdb_upsert chunks to local scope
   f. kg_upsert_nodes and kg_upsert_edges to local scope
   g. Report progress: file count, chunk count, node count, edge count
6. Update last_indexed_at in the registry
7. Print summary: total files, chunks, nodes, edges, skipped files, elapsed time
```

### 1.5 Inference rules for `implements_spec` edges

Archaeology makes a best-effort attempt to infer which code symbols implement which specs. It does not require perfect inference -- a missed edge is better than a wrong one. The following signals are used:

| Signal | Example | Edge created |
|---|---|---|
| Docstring references a spec identifier | `"""Implements AUTH-001."""` | `symbol -> spec/AUTH-001` |
| Symbol name matches a spec identifier pattern | function `handle_auth_001` | `symbol -> spec/AUTH-001` (low confidence, flagged) |
| Comment in function body cites a spec | `# per AUTH-001` | `symbol -> spec/AUTH-001` |
| Test file name references a spec | `test_auth_001.py` | `module -> spec/AUTH-001` |

Low-confidence edges are stored with `attrs.confidence = "low"`. Callers may filter these out. High-confidence edges (docstring, explicit comment) carry `attrs.confidence = "high"`.

### 1.6 Output

Progress is reported turn by turn as Claude works through the repository. The final summary includes:

```
Archaeology complete.
  Files processed:  142 (118 code, 12 spec, 12 doc)
  Files skipped:    8 (excluded by pattern)
  Chunks written:   1,840
  Nodes upserted:   634
  Edges upserted:   1,203
  Elapsed:          2m 14s
```

### 1.7 Re-running archaeology

Archaeology is idempotent. All VDB upserts and KG upserts are keyed on artifact identity. Running archaeology a second time on an unchanged repo produces the same index state. Running it after changes updates only the changed artifacts; unchanged artifacts are re-upserted (idempotent, no side effect).

For large repositories, it is more efficient to let the ingest hooks maintain the index incrementally after the first archaeology run rather than re-running archaeology on every change.

### 1.8 Failure handling

| Failure | Behavior |
|---|---|
| VDB or KG not provisioned | Stop immediately, instruct user to run `cartographer init` |
| A single file fails to ingest | Log the file path and error, continue with remaining files |
| Binary extraction fails (Claude tool error) | Log file path, skip, continue |
| Embedder unavailable | Stop, report error. Do not leave partial results without reporting. |
| Repository has no recognized files | Print message, exit cleanly |

---

## 2. Skill: `recall`

### 2.1 Purpose

Answer "what did we do on X?" by querying the registry and the appropriate index, respecting tenant isolation. Used for deliberate cross-project or cross-session recall, complementing the automatic per-turn retrieval the `retrieve` hook provides.

The `retrieve` hook handles passive, in-context recall on every turn. The `recall` skill handles active, intentional recall when the developer explicitly wants to find something.

### 2.2 Invocation

```
/recall <query>
```

Or via natural language: "what did we do about auth in the payments project?", "recall how we handled rate limiting", "find prior work on database migrations".

### 2.3 Inputs

| Input | Source | Description |
|---|---|---|
| Query | User prompt or argument | Natural language query |
| Current project context | `cartographer.toml` | Used to determine current tenant for isolation check |
| Registry | `~/.cartographer/registry.db` | Source of project list |

### 2.4 Process

```
1. Load current project config to determine current tenant
2. Read registry: list all projects where project.tenant matches current tenant
   Projects with a different tenant are excluded and must never be queried
3. If no matching projects: report "no projects found for tenant <tenant>" and stop
4. For each matching project (including the current project):
   a. Load the project's index connection (local path or central endpoint)
   b. vdb_query(text=<query>, k=5, scope=local)
   c. If central topology: vdb_query(text=<query>, k=5, scope=global)
   d. kg_neighbors for the top 3 VDB results (depth 1)
5. Merge all results across projects, deduplicate by artifact identity
6. Rank merged results by score
7. Tag each result with: project name, project_id, scope (local/global), origin
8. Present results to the user with attribution
```

### 2.5 Isolation enforcement

Isolation is enforced at step 2. The tenant check is not advisory -- it is a hard gate. The recall skill must never issue a query against a project whose `tenant` differs from the current project's `tenant`, regardless of how the user phrases the request.

If a user asks to recall from a project on a different tenant explicitly (e.g., "recall from the Acme project" when the current project is under a different tenant), the skill responds:

```
Cross-tenant recall is not permitted. The project "Acme" belongs to a different tenant.
```

No query is issued, no results are returned, and the attempt is logged to `~/.cartographer/audit.log`.

### 2.6 Output format

Results are presented as a structured summary, attributed by project and origin:

```
Recall results for: "how did we handle rate limiting"

From: payments-api (this project, local)
  src/middleware/rate_limit.py#RateLimiter.check()  [score: 0.91]
  "Checks the sliding window counter for the requesting client.
   Raises RateLimitExceeded if the limit is exceeded within the window."

From: auth-service (project: auth-service, global)
  src/throttle.py#ThrottleMiddleware  [score: 0.84]
  "Token bucket throttle applied per API key. Configurable burst and
   sustained rate via THROTTLE_BURST and THROTTLE_RATE env vars."

From: payments-api (this project, local)
  docs/architecture.md#Rate Limiting  [score: 0.79]
  "Rate limiting is applied at the gateway layer using a sliding window
   algorithm with a 60-second window..."
```

Each result shows: source project, file path and symbol, score, origin tag (local/global), and the first two lines of the chunk text.

### 2.7 Failure handling

| Failure | Behavior |
|---|---|
| Registry is empty or missing | Report no projects found, stop |
| A project's index is unreachable (path moved, backend down) | Log warning, skip that project, continue with others |
| Cross-tenant query attempt | Block query, report reason, log to audit log |
| No results found across all projects | Report "no relevant prior knowledge found for this query" |

---

## 3. Skill file structure

Skills live in the plugin package under `skills/`. Each skill is a directory containing a `SKILL.md` file, which is the Claude Code skill definition.

```
cartographer-plugin/
  skills/
    archaeology/
      SKILL.md      # skill definition: instructions, tools, invocation pattern
    recall/
      SKILL.md      # skill definition: instructions, tools, invocation pattern
```

### 3.1 `SKILL.md` contract

Each `SKILL.md` must define:

| Section | Content |
|---|---|
| Purpose | One paragraph describing what the skill does and when to use it |
| Invocation | Slash command name and natural language triggers |
| Steps | Numbered, explicit instructions for Claude to follow |
| Tools | Which MCP tools the skill uses (vdb_query, kg_neighbors, etc.) |
| Isolation rules | Any tenant or scope checks that must run before queries |
| Output format | What the skill should present to the user |
| Failure handling | How to handle each named failure mode |

Skills must be self-contained. Claude executing a skill should not need to read any other document to complete the skill's steps correctly.

---

*For the hooks that provide automatic (non-deliberate) recall, see [hooks.md](hooks.md). For the MCP tool contracts that skills call, see [contracts/vdb-tools.md](../contracts/vdb-tools.md) and [contracts/kg-tools.md](../contracts/kg-tools.md).*
