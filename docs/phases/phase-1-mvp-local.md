# Phase 1: MVP, Local Only

## Goal

Prove the recall loop. A developer installs Cartographer, works in a Claude Code session, and relevant prior knowledge surfaces automatically without them asking for it. Everything runs on the developer's machine with no external service, no cloud account, and no network dependency.

The single most important acceptance gate: a developer working in a real Claude Code session asks a question about prior work and Claude answers using recalled knowledge it was not explicitly told about in the current session.

---

## References

| Document | What to read |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Sections 1-5: layers, behavior rule, state layer, local topology |
| [APPLICATION_ARCHITECTURE.md](../APPLICATION_ARCHITECTURE.md) | Part 1: CLI flows; Part 3: hook runtime flows |
| [DATA_MODEL.md](../DATA_MODEL.md) | Sections 2-5: artifact identity, VDB schema, KG schema, registry |
| [CONFIGURATION.md](../CONFIGURATION.md) | Full reference for cartographer.toml and local override |
| [SECURITY_AND_ISOLATION.md](../SECURITY_AND_ISOLATION.md) | Sections 2-5: tenant isolation, egress, secrets, working state |
| [components/cli.md](../components/cli.md) | All commands: init, detect, stack add, seed, recall, doctor |
| [components/hooks.md](../components/hooks.md) | All four hooks: enqueue, flush, preload, retrieve |
| [components/mcp-servers.md](../components/mcp-servers.md) | VDB and KG server specs, LanceDB and Kuzu drivers |
| [components/skills.md](../components/skills.md) | Archaeology and recall skill specs |
| [contracts/vdb-tools.md](../contracts/vdb-tools.md) | Full VDB tool contract |
| [contracts/kg-tools.md](../contracts/kg-tools.md) | Full KG tool contract |
| [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) | OQ-01 through OQ-07: all must be resolved before implementation starts |

---

## Scope

### In scope

| Component | What ships |
|---|---|
| CLI | `init`, `detect`, `stack add`, `seed`, `promote` (no-op), `recall`, `ui`, `doctor` |
| Standards packs | Cross-stack baseline, Python pack, React pack -- bundled |
| Plugin package | `plugin.json`, `hooks.json`, MCP server entry points, skill files |
| Hooks | Ingest enqueue (`PostToolUse`), ingest flush (`Stop`), preload (`SessionStart`), retrieve (`UserPromptSubmit`) |
| MCP servers | VDB server with LanceDB driver; KG server with Kuzu driver |
| Ingestion pipeline | Code, spec, and plain-text doc ingestion; symbol extraction; KG node and edge extraction; fastembed embedder |
| Skills | `archaeology`, `recall` |
| Registry | Per-machine SQLite registry at `~/.cartographer/registry.db` |
| Config | `cartographer.toml`, `.cartographer.local.toml` stub, `cartographer.example.toml` |
| Security | Tenant isolation in recall skill; no-egress default; secret scan in doctor |

### Explicitly out of scope

- Central backend drivers (Qdrant, pgvector, Neo4j, Neptune, Aurora)
- Promotion to a global index (promote command is a no-op)
- Binary document extraction (`.docx`, `.pptx`, `.pdf`) -- plain text only
- Standards Registry and Standards web app
- Multi-developer shared knowledge layer

---

## Component breakdown

### 1. CLI package (`cli/`)

**What to build:**

| Command | Key implementation tasks |
|---|---|
| `detect` | Workspace scanner; report formatter |
| `init` | Config writer; workspace scaffolder; CLAUDE.md merger; settings.json merger; mcp.json merger; VDB + KG provisioning calls; registry upsert; gitignore writer |
| `stack add` | Pack resolver (bundled only in Phase 1); pack file copier; `active_stacks` updater |
| `seed` | File resolver; plain-text reader; ingestion pipeline invocation; progress reporter; `--enrich` flag wiring to Claude-based KG enricher |
| `promote` | No-op with topology check; clear message that central is not configured |
| `recall` | Registry reader; tenant check; VDB query; KG neighborhood query; result merger; output formatter |
| `ui` | FastAPI server; static file serving from `cli/src/cartographer/ui/`; VDB search endpoint; KG graph endpoint; registry endpoint; stats endpoint; browser open on start |
| `doctor` | Config schema validator; secret pattern scanner; gitignore checker; VDB + KG reachability checker; dimension match checker; registry checker |

**Driver implementations required:**
- `cli/src/cartographer/drivers/vdb/lancedb.py` -- full implementation of VDB driver base
- `cli/src/cartographer/drivers/kg/kuzu.py` -- full implementation of KG driver base
- `cli/src/cartographer/drivers/embedder/fastembed.py` -- full implementation of embedder base

**Ingestion pipeline required:**
- `text_extractor.py` -- plain text only in Phase 1; binary returns a skip warning
- `chunker.py` -- code (symbol boundary), spec (section boundary), doc (heading boundary)
- `embedder.py` -- wraps fastembed driver
- `graph_extractor.py` -- regex-based node and edge extraction; optional Claude enrichment via `kg_enricher.py`
- `kg_enricher.py` -- calls `claude -p` subprocess to extract semantic relationships; returns structured `EnrichmentResult`; falls back silently if `claude` is not on PATH
- `pipeline.py` -- orchestrates the full extract -> chunk -> embed -> upsert sequence; threads `enrich` flag through to `graph_extractor`

**Reference:** [components/cli.md](../components/cli.md), [APPLICATION_ARCHITECTURE.md sections 1.1-1.3](../APPLICATION_ARCHITECTURE.md)

---

### 2. Plugin package (`cartographer-plugin/`)

**What to build:**

| File | Key implementation tasks |
|---|---|
| `.claude-plugin/plugin.json` | Manifest with version, component list, min Claude Code version |
| `hooks/hooks.json` | Four hook registrations using `${CLAUDE_PLUGIN_ROOT}` references |
| `scripts/ingest_enqueue.py` | PostToolUse handler; dirty queue writer; artifact type inference |
| `scripts/ingest_flush.py` | Dirty queue reader; debounce check; pipeline invocation; queue clear on success |
| `scripts/preload.py` | Config loader; env file writer; working set detection via git; VDB + KG queries; token budget formatter; stdout injection |
| `scripts/retrieve.py` | Prompt reader; VDB query; KG neighborhood query; result merger; token budget formatter; stdout injection |
| `mcp-servers/vdb_server.py` | MCP server entry point; driver loader; tool handler registration; startup health check |
| `mcp-servers/kg_server.py` | MCP server entry point; driver loader; tool handler registration; startup health check |
| `skills/archaeology/SKILL.md` | Full skill definition per [components/skills.md](../components/skills.md) |
| `skills/recall/SKILL.md` | Full skill definition per [components/skills.md](../components/skills.md) |

**Reference:** [components/plugin.md](../components/plugin.md), [components/hooks.md](../components/hooks.md), [components/mcp-servers.md](../components/mcp-servers.md), [components/skills.md](../components/skills.md)

---

### 3. Standards packs (`standards/`)

**What to build:**

| Pack | Files required |
|---|---|
| `cross-stack` | `README.md`, `standards.md` (5 sections), `CHANGELOG.md` |
| `python` | `README.md`, `standards.md` (6 sections), `CHANGELOG.md` |
| `react` | `README.md`, `standards.md` (6 sections), `CHANGELOG.md` |

Each pack must also be copied to `cli/src/cartographer/standards_packs/<pack-name>/`.

**Reference:** [components/standards-packs.md](../components/standards-packs.md)

---

### 4. MCP tool contracts

The VDB and KG tool contracts defined in `docs/contracts/` are the interface the MCP servers implement. Before any server or driver code is written, verify the contracts are complete and unambiguous. Flag any gap as an update to the contract documents -- do not silently resolve it in code.

**Reference:** [contracts/vdb-tools.md](../contracts/vdb-tools.md), [contracts/kg-tools.md](../contracts/kg-tools.md)

---

## Build order

Components have dependencies. Build in this order to avoid blocked work:

```
1. Config loader + schema (blocks everything)
2. VDB driver (LanceDB) + KG driver (Kuzu) + embedder (fastembed)
3. Ingestion pipeline (depends on drivers)
4. MCP servers -- VDB and KG (depends on drivers)
5. CLI: init + detect (depends on config, drivers)
6. CLI: stack add (depends on init)
7. CLI: seed (depends on ingestion pipeline)
8. CLI: doctor (depends on all of the above)
9. Hook scripts (depends on ingestion pipeline, MCP servers)
10. Plugin package assembly (depends on hook scripts, MCP servers, skills)
11. CLI: recall (depends on registry, VDB + KG drivers)
12. CLI: ui -- FastAPI server + static UI files (depends on VDB + KG drivers; can run in parallel with step 11)
13. Skills: archaeology + recall (depends on plugin being assembleable)
14. Standards pack content (independent; can run in parallel with any of the above)
```

---

## Open questions to resolve before starting

All Phase 1 blockers from [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) must be resolved before implementation starts:

| Question | Blocks |
|---|---|
| OQ-01: Promotion trigger default | `cartographer init` default config output |
| OQ-02: Retrieval token budgets | Hook scripts, `cartographer.example.toml` defaults |
| OQ-03: Spec file format and detection | Ingest hook artifact type inference; archaeology traversal |
| OQ-04: Registry location | Registry module; `cartographer.example.toml` |
| OQ-05: Marketplace hosting | `.mcp.json` entry template in `cartographer init` |
| OQ-06: Standards pack versioning | `stack add` command; pack CHANGELOG format |
| OQ-07: Binary extraction outside session | `seed` command failure mode |

---

## Exit criteria

All criteria must be demonstrated against a real project, not a synthetic test.

| # | Criterion | How to verify |
|---|---|---|
| 1 | `cartographer init` completes on a greenfield project | Run from an empty git repo; confirm all expected files are created |
| 2 | `cartographer init` merges additively on an existing project with Claude config | Add a `CLAUDE.md` and `.claude/settings.json` manually; run init; confirm contents are merged, not overwritten; confirm backups exist |
| 3 | Cross-stack and Python pack are written into `.claude/standards/` | `ls .claude/standards/` after init with `--stack python` |
| 4 | `cartographer doctor` passes all checks on a correctly initialized project | Run `cartographer doctor`; confirm exit code `0` and all checks green |
| 5 | A new Claude Code session injects preloaded context from the local index | Open a session on a seeded project; observe the `[Cartographer: session context]` block in the first turn |
| 6 | After editing a file, the ingest hook updates the local index by end of turn | Edit a file; end the turn; run `cartographer recall "<something from the edit>"`; confirm result appears |
| 7 | A fresh session recalls knowledge from a prior session | Ingest in session A; close session A; open session B; confirm prior knowledge appears in preload context |
| 8 | `cartographer seed <docs-path>` ingests markdown files into the local index | Seed a directory of markdown files; run `cartographer recall "<query about doc content>"`; confirm results reference seeded content |
| 9 | `cartographer recall "<query>"` returns ranked results with origin tags | Run against a seeded project; confirm output includes path, score, and origin |
| 10 | Recall skill blocks cross-tenant query | Initialize two projects with different tenants; invoke `/recall` on project A asking about project B content; confirm the block message and audit log entry |
| 11 | `/archaeology` indexes an existing codebase end to end | Run on a real Python project; confirm node and chunk counts are non-zero; run `cartographer recall` to verify results |
| 12 | `cartographer ui` starts a local server, opens a browser, and displays seeded content in the search view | Run `cartographer ui`; search for a term from a seeded doc; confirm a result appears with path, score, and chunk text |
| 13 | The recall loop works live | Open a session; ask a question about prior work; confirm Claude answers using recalled knowledge without being told about it explicitly |

Criterion 12 is the acceptance gate for the entire phase. It must be demonstrated last, after all other criteria pass.

---

## Test approach

### Unit tests

Location: `cli/tests/unit/`

| Area | What to test |
|---|---|
| Config loader | Precedence order (env > local override > toml > default); missing file handling; schema validation errors |
| Artifact type inference | Path patterns for spec, doc, code classification; edge cases (file in `specs/` with `.py` extension) |
| Chunker | Symbol boundary chunking for Python; heading boundary chunking for markdown; sliding window fallback |
| Graph extractor | Node extraction from a Python file (module, symbols); edge extraction (defines, references); spec node extraction from a markdown spec |
| Tenant isolation | Recall blocks when tenants differ; recall proceeds when tenants match |
| Dirty queue | Enqueue writes correctly; flush reads and clears; debounce logic |
| Token budget | Preload context truncates at budget; lowest-score results dropped first |

### Integration tests

Location: `cli/tests/integration/`

Tests run against real LanceDB and Kuzu instances on disk (no mocks). Use a temp directory per test.

| Area | What to test |
|---|---|
| VDB driver (LanceDB) | `ensure_collection`, `upsert`, `query` returns correct chunks, `delete` removes by id, dimension mismatch error |
| KG driver (Kuzu) | `ensure_namespace`, `upsert_nodes`, `upsert_edges`, `neighbors` at depth 1 and 2, cascade delete |
| Ingestion pipeline | Full pipeline from a Python file to VDB chunks + KG nodes; idempotent upsert (run twice, same result) |
| `cartographer init` | Greenfield project: all files created; existing project: additive merge only, no overwrite |
| `cartographer seed` | Plain text directory ingested; unsupported extensions skipped with warning |
| `cartographer doctor` | All checks pass on a clean init; secret pattern in toml triggers failure |
| `cartographer recall` | Query returns results from seeded content; cross-tenant query returns block |

### Hook tests

Location: `cli/tests/hooks/`

Hook scripts are Python files invoked as subprocesses. Tests invoke them directly with environment variables set.

| Hook | What to test |
|---|---|
| ingest_enqueue | Dirty queue file is written with correct artifact type; re-enqueue of same file updates timestamp |
| ingest_flush | Queue is drained and cleared after flush; debounce skips flush when newest entry is too recent; failed upsert leaves queue intact |
| preload | Env file is written with correct keys; context block is within token budget; empty index returns empty context without error |
| retrieve | Query against seeded index returns relevant chunks; context block is within token budget; failure exits 0 silently |

### MCP server tests

Location: `cli/tests/mcp/`

Tests invoke the MCP server tools directly via the Python server module (not via Claude Code).

| Server | What to test |
|---|---|
| VDB server | All five tools: ensure_collection, upsert, query, delete, collection_stats; scope write protection (global write rejected); dimension mismatch error |
| KG server | All eight tools: ensure_namespace, upsert_nodes, upsert_edges, query, neighbors, delete_nodes, delete_edges, namespace_stats; depth > 4 rejected; cascade delete on node delete |

### End-to-end acceptance test

One test, run manually at phase close. Documented as a runbook.

```
1. Create a new git repo at /tmp/phase1-test
2. Add a Python module with 3-5 functions and a spec file that one function references
3. Run: cartographer init --stack python --yes
4. Run: cartographer seed docs/ (if docs exist)
5. Open a Claude Code session in /tmp/phase1-test
6. Verify: session context block appears in first turn
7. Edit one of the Python functions in the session
8. End the turn; verify ingest flush ran (check cli.log)
9. Run: cartographer recall "how does <function name> work"
10. Verify: the edited function appears in results
11. Close the session; open a new session
12. Verify: prior knowledge appears in preload context
13. In the new session, ask about the function without mentioning its name
14. Verify: Claude answers correctly using recalled knowledge
```

Pass criterion: step 14 succeeds. Claude does not say "I don't have information about that."

---

*For phase exit criteria summary, see [ROADMAP.md](../ROADMAP.md). For open questions, see [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md).*
