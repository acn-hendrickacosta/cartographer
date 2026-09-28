# Project Brief: Cartographer

> Working codename. Rename freely. `cartographer` is used throughout as the package/CLI name placeholder.

| Field | Value |
|---|---|
| Status | Draft v0.2. CLI (Section 6.1, local topology) implemented and verified end to end; plugin, docs set, and standards web app not yet started. |
| Owner | Hendrick |
| Type | CLI + shared standards + a standards web app for SME-managed, cloud-hosted standards |
| Audience for this doc | Claude Code, running in the working directory, tasked with generating the formal project documentation set and repo scaffold |
| License intent | Internal first, open to contribution later |

---

## 0. How Claude Code should use this brief

This document is the source of truth for kickoff. Read it end to end before generating anything. Your job in this session is not to build the whole system. Your job is to turn this brief into a formal, reviewable documentation set and an empty-but-correct repository scaffold, so a team can start implementing against agreed contracts.

Concrete deliverables for this session are listed in Section 16. Do not implement business logic, do not write real ingestion or embedding code, and do not stand up services. Generate documents, contracts, schemas as text, stub files with docstrings and TODOs, and a directory tree. Where this brief leaves a decision open, surface it in `docs/OPEN_QUESTIONS.md` rather than silently choosing.

Follow the writing conventions in Section 15 for every document you produce.

---

## 1. Problem statement

Teams building software with Claude Code lose context between sessions and between people. Claude re-reads files it has already understood, forgets decisions made in earlier sessions, and has no durable model of how a codebase and its specifications relate. On spec-driven projects this is worse, because the specification is the highest-signal artifact and it is exactly the thing that is not carried forward reliably.

There is a well-understood reason a naive fix fails. Skills and instructions are model-invoked, so asking Claude to "remember to update the knowledge base" is not a guarantee. The knowledge can sit one tool call away and still not be recalled. Reliability for always-on behavior has to come from deterministic hooks, not from prompting.

Cartographer is a reusable, installable package that gives any Claude Code project a persistent knowledge layer: a lightweight knowledge graph and a vector index that are kept current automatically as code and specs change, and that Claude consults automatically while working. It ships with cross-stack development standards and per-stack packs, and it installs in one step into either a new project or an existing workspace.

## 2. Goals and non-goals

### Goals

1. One-command setup into a greenfield project or an existing workspace, without clobbering existing Claude configuration.
2. A persistent, self-updating knowledge layer per project: a knowledge graph plus a vector index, populated from code and specs.
3. Deterministic capture of changes, so the knowledge layer stays current without relying on the model to remember.
4. Automatic recall, so relevant prior knowledge is surfaced to Claude during coding rather than left for it to find.
5. Reusable development standards, cross-stack by default plus per-stack packs, contributable over time. Python and React are the first two packs.
6. Configurable topology: local embedded by default, with an opt-in central knowledge layer for multi-developer projects.
7. Cross-project recall, so a developer can ask what they did on prior projects, subject to isolation rules.

### Non-goals (for the initial phases)

1. Real-time bidirectional sync between local and central indexes. See Section 7.4 and the roadmap.
2. Cross-client or cross-tenant shared recall. Isolation is a hard boundary, see Section 11.
3. Replacing version control, code search, or a project wiki. Cartographer complements them.
4. Supporting every stack at launch. Contributors add stacks.
5. A hosted product. This is a package teams self-install.

## 3. Users and scenarios

| User | Scenario | Primary path |
|---|---|---|
| Solo dev, new project | Starts greenfield, wants standards and a growing knowledge base from day one | `cartographer init`, local index, specs and code ingested as written |
| Solo dev, existing repo | Inherits a codebase, wants Claude to understand it fast | `cartographer init` then run the archaeology skill to bootstrap the KB |
| Team, shared project | Several developers on one codebase, want a common knowledge layer | `init` with central backend configured, local index per developer, promotion to global on merge |
| Any dev, recall | Wants to remember what they did on a past project | Recall skill queries the project registry and the appropriate index, within isolation rules |

## 4. Core concepts and glossary

| Term | Meaning |
|---|---|
| KG | Knowledge graph. Lightweight by default. Nodes are code, spec, and documentation artifacts, edges are relationships (defines, references, implements-spec, depends-on). |
| VDB | Vector database. Local embedded by default. Stores embedded chunks of code, specs, and documentation for semantic recall. |
| Local index | The KG and VDB for a developer's working state, including unmerged changes. Private to that developer's machine by default. |
| Global index | The shared KG and VDB representing merged, canonical project state. Lives in the central backend when configured. |
| Promotion | The act of moving knowledge from local to global. Triggered by merge to the main branch. Not live sync. |
| Artifact identity | The stable key for a KG node or a VDB chunk: file path plus symbol, or spec id. Not a commit SHA. Makes promotion idempotent. |
| Spec | A specification artifact in the spec-driven workflow. First-class, higher-signal than code, watched specifically by ingestion. |
| Documentation artifact | Any project documentation file ingested into the KG and VDB. Supported formats: .md, .rst, .txt, .adoc (plain text, read directly) and .docx, .pptx, .pdf (binary, text extracted via Claude local before chunking). First-class alongside code and specs. Can be seeded explicitly by a developer via `cartographer seed`. |
| Archaeology | The bootstrap process that reads an existing codebase and builds the initial KG and VDB. |
| Standards pack | A versioned set of development standards. A cross-stack baseline plus per-stack packs (python, react). |
| Registry | An index of projects a developer or team has worked on, used for cross-project recall. |
| Standards Registry | A versioned, cloud-hosted index of standards pack content (candidate: S3 or an S3-compatible store), separate from the project registry above. Becomes the source of truth for standards once the standards web app ships; until then, the CLI's bundled packs are the source of truth. See Section 5.6. |
| Standards web app | A separate application, not the CLI and not the plugin, where SMEs author, review, and publish standards pack versions into the Standards Registry. See Section 6.7. |

## 5. Architecture overview

Three layers, mapped to Claude Code primitives.

### 5.1 Distribution layer

- The **CLI** (`cartographer`) is the single distribution mechanism. `cartographer init` scaffolds the workspace, merges existing Claude configuration, provisions the per-project index, registers the project, and writes all hook, MCP, and skill configuration directly into the workspace.

A separate Claude Code plugin format was considered and deferred. The CLI already handles everything the plugin would have bundled. The plugin format can be revisited as a marketplace distribution option in a later phase, if there is demand for installation without pip.

### 5.2 Behavior layer: skills versus hooks

The single most important design rule. Model-invoked work goes in skills. Guaranteed always-on work goes in hooks.

| Capability | Mechanism | Event or invocation | Why |
|---|---|---|---|
| Code archaeology to bootstrap the KB | Skill or slash command | User or Claude invokes once | Deliberate, one-time, needs judgment |
| Update KG and VDB on change | Hook | PostToolUse marks dirty, flush on Stop or git commit | Must be a guarantee, not a hope |
| Preload relevant knowledge | Hook | SessionStart injects a scoped context slice | Recall must happen without the model asking |
| Per-turn retrieval | Hook | UserPromptSubmit injects budgeted top-k | Keeps recall fresh, controls token cost |
| Reference knowledge on demand | MCP query tools | Model calls when it decides it needs more | For deeper, targeted lookups |
| Cross-project recall | Skill plus MCP tool | User asks | Deliberate, needs isolation checks |

Design notes for the ingestion hook:
- PostToolUse fires after every Write and Edit and is observe-only. Treat it as enqueue-only: mark files dirty, do not embed inline.
- Flush the embed and KG update on the Stop event (turn boundary) or on a git commit matcher. Debounce so a burst of edits produces one flush.
- Watch spec files specifically. In spec-driven work the spec is the anchor.
- Documentation files are first-class artifacts. The hook watches them alongside code and specs. Supported formats: .md, .rst, .txt, .adoc, .docx, .pptx, .pdf.
- Binary formats (.docx, .pptx, .pdf) are processed by invoking Claude locally for text extraction before chunking. No external model or API is used.
- Developers can also seed documentation explicitly without waiting for the hook to observe edits, using `cartographer seed`.

### 5.3 State layer

The KG and VDB are stateful services reached through **MCP servers** bundled in the plugin, so the tool access travels with the package.

Defaults are lightweight and local:

| Store | Local default | Central upgrade path |
|---|---|---|
| VDB | Embedded (LanceDB or Qdrant embedded), on-disk in the workspace | Any backend implementing the VDB driver contract: Qdrant, Milvus, pgvector, OpenSearch, Weaviate |
| KG | Embedded property graph (Kuzu) or a SQLite-backed triple store | Any backend implementing the KG driver contract: Neo4j, PuppyGraph, Neptune, ArangoDB |
| Embeddings | Local embedding model (fastembed or sentence-transformers) to avoid data egress | Same, or a configured API embedder if the team accepts egress |

Both local and central backends implement the same driver interface. Switching topology is a configuration change, not a code change. The central backend is accessed over HTTPS using an API key configured in the gitignored local override or the environment.

Backend selection is driven by config (Section 10) behind a driver interface, so local and central share one contract and swapping is a configuration change, not a rewrite. Default the embedder to local, because for client code the confidentiality cost of shipping source to an embedding API is usually unacceptable.

### 5.4 Two-pronged local and global model

The core of the shared-team design, and the answer to the sync problem.

- **Local index**: a developer's working state, including unmerged work. Private to their machine. Always present, even when a central backend is configured.
- **Global index**: merged, canonical project state. Present only when a central backend is configured.
- **Promotion boundary is the merge**, not a background sync. When a branch merges to the main branch, a promotion step re-indexes the merged artifacts into the global index.
- **Keying makes it safe**. KG nodes and VDB chunks are keyed by artifact identity (file path plus symbol, or spec id), never by commit SHA. Promotion becomes an idempotent upsert. Squash merges, which collapse history, do not corrupt the global index because identity does not depend on the collapsed commits.
- **Promotion trigger** is a git post-merge hook, a CI step on merge to the main branch, or an explicit `cartographer promote` command. Pick one per team in config. Do not attempt live sync.
- **Read order** during coding: local first (freshest, includes unmerged work), then global (canonical), with results tagged by origin so Claude and the developer can tell working knowledge from merged knowledge.

Deferred, and explicitly out of scope for the first phases: true bidirectional reconciliation, handling deletions and renames across the boundary, rebase and history-rewrite handling, and conflict resolution when local and global disagree. The keying decision above is what keeps this deferral cheap.

### 5.5 Deployment topologies

| Topology | When | Config |
|---|---|---|
| Local only (default) | Solo dev, or teams not ready for shared infra | Local VDB and KG, no global index, no promotion |
| Central, opt-in | Multi-dev project wanting shared knowledge | Local per developer plus a configured central VDB and KG, promotion on merge |

### 5.6 Standards distribution

A separate concern from the KG/VDB topology in 5.4 and 5.5, and phased independently of it.

- **Today**: standards packs (cross-stack, python, react) are bundled inside the CLI package itself, at `cli/src/cartographer/standards_packs/`. `cartographer init` and `cartographer stack add <name>` copy the bundled markdown into the workspace. This is real, tested, end-to-end behavior, not a stub. Its limitation is that changing a standard requires a new CLI release.
- **Later, phased**: a **Standards Registry**, a versioned, cloud-hosted index of pack content, becomes the source of truth. A companion **Standards web app**, a separate application from the CLI and the plugin, is where SMEs author, review, and publish pack versions into the registry without needing repo or CLI-release access.
- When the registry ships, the CLI fetches from it (`stack add`, `init`) and falls back to its bundled defaults when the registry is unset or unreachable, so a project never breaks because a network call failed.
- Per the phasing principle in Section 11, this is deferred as a whole feature, not half-built. The CLI's current bundled-standards behavior remains the real, complete implementation until the registry and web app are built as their own complete phase.

## 6. Component specifications

Generate a specification document per component under `docs/components/`. Each should define purpose, inputs, outputs, contracts, config surface, failure modes, and open questions. Summaries below.

### 6.1 CLI (`cartographer`)

Commands for the first cut:

| Command | Behavior |
|---|---|
| `init` | Detect existing Claude config, scaffold the cross-stack `.claude` baseline, apply selected stack packs, provision the per-project local index, write config, register the project. Idempotent. |
| `detect` | Report existing `.claude`, `CLAUDE.md`, `.mcp.json`, and settings found in the workspace, and what `init` would merge versus create. Dry run. |
| `stack add <name>` | Apply a stack pack (python, react) into the workspace standards. |
| `promote` | Manual promotion of merged artifacts to the global index. No-op in local-only topology. |
| `recall` | Convenience wrapper to query the registry, mostly a debugging aid. The real path is the recall skill. |
| `seed <path>` | Ingest a documentation source (directory, file, or glob) into the local index immediately, outside of the normal hook-triggered ingestion cycle. |
| `ui` | Launch a lightweight local web server (FastAPI + single-page HTML/JS) that lets a developer browse the local VDB and KG visually: semantic search, graph explorer, registry view, and index stats. |
| `doctor` | Validate config, backend reachability, and plugin wiring. |

Setup rules:
- Never clobber. If `CLAUDE.md`, `.claude/settings.json`, or `.mcp.json` exist, back them up, then merge additively and dedupe MCP entries. Report every change.
- The cross-stack `.claude` baseline is always created on `init`, regardless of stacks selected.
- Provision the per-project index (collection or table plus KG namespace) named deterministically from the project id.
- Write connection and scope config so a SessionStart hook can inject the right index names at runtime.

### 6.2 Runtime bundle layout

All runtime assets ship inside the CLI package under `cli/src/cartographer/runtime/`. There is no separate plugin directory. `cartographer init` reads from this bundle and writes the appropriate configuration into the target workspace.

```
cli/src/cartographer/runtime/
├── hooks.json             # hook definitions; init merges these into .claude/settings.json
├── mcp_servers/           # MCP server entry points; installed as named commands via pyproject.toml scripts
│   ├── vdb_server.py
│   └── kg_server.py
├── scripts/               # hook runner implementations; called via `cartographer hook <name>`
│   ├── post_tool_use.py
│   ├── on_stop.py
│   ├── session_start.py
│   └── user_prompt_submit.py
└── skills/
    ├── archaeology/SKILL.md
    └── recall/SKILL.md
```

### 6.3 Skills

- **archaeology**: bootstraps the KB from an existing codebase. Walks the repo, extracts artifacts and relationships into the KG, chunks and embeds into the VDB, and infers implicit specs where possible. Invoked deliberately. Spec should define traversal strategy, what becomes a node, what becomes an edge, and how to chunk.
- **recall**: answers "what did I do on X" by querying the registry then the appropriate index, respecting isolation. Spec should define the isolation check, the query flow, and how results are attributed by origin.

### 6.4 Hooks

- **ingest** (PostToolUse enqueue, Stop or commit flush): captures code and spec changes into local KG and VDB. Debounced. Idempotent upserts keyed by artifact identity.
- **preload** (SessionStart): injects a scoped, budgeted context slice for the current branch and working set.
- **retrieve** (UserPromptSubmit): injects budgeted top-k relevant knowledge per turn.

Portability: hooks are invoked as `cartographer hook <name>`, so no hardcoded paths are needed. Read project root via `$CLAUDE_PROJECT_DIR`, persist env from SessionStart via `$CLAUDE_ENV_FILE`.

### 6.5 MCP servers

Two servers, or one server with two tool groups. Define tool contracts in `docs/contracts/`.

- **vdb**: `upsert(chunks)`, `query(text, k, scope)`, `delete(ids)`, `ensure_collection(project_id, scope)`. Scope is local or global.
- **kg**: `upsert_nodes(nodes)`, `upsert_edges(edges)`, `query(pattern, scope)`, `neighbors(node_id, depth, scope)`, `ensure_namespace(project_id, scope)`.

Both servers take a scope argument so the same tools serve local and global reads and writes.

### 6.6 Standards packs

```
standards/
├── cross-stack/     # always applied: git hygiene, spec-driven workflow, review, security baseline, Claude Code usage norms
├── python/
└── react/
```

Each pack is markdown plus optional skills and hooks. Packs are versioned so a project can pin a version.

Today, these packs are bundled inside the CLI package (`cli/src/cartographer/standards_packs/`) and contributed by PR, per Section 5.6. Once the Standards Registry and web app (Section 6.7) ship, packs are authored and published there instead; PR-based contribution remains the fallback path for the CLI's bundled defaults.

### 6.7 Standards web app

A separate application from the CLI and the plugin. Not part of the deliverable set in Section 16; generate its own specification document under `docs/components/` once this phase is scheduled.

Purpose: let SMEs author, review, and publish standards pack content into the Standards Registry (Section 5.6) without needing repo or CLI-release access.

Summary of what its spec needs to define when this phase starts:
- Authoring flow: create or edit a pack's markdown content, per stack.
- Review flow: a draft state before a version is published, and who can approve it.
- Publish flow: writes a new, immutable version of the pack into the Standards Registry, keyed by pack name and version.
- Read path: the CLI fetches published versions from the registry; the web app may also serve a browsable, human-readable view of current standards.
- Auth: who can author, who can approve. Open, see Section 14.

## 7. Data model

Generate `docs/DATA_MODEL.md`.

### 7.1 VDB

- One logical collection per project, namespaced by scope (local, global).
- Chunk record: `id` (artifact identity plus chunk ordinal), `project_id`, `scope`, `artifact_type` (code, spec, doc), `path`, `symbol` (nullable), `spec_id` (nullable), `origin` (local or global), `text`, `embedding`, `updated_at`.
- `artifact_type: doc` covers any project documentation file ingested via hook or explicit seed. Docs are queried through the same VDB and KG tools as code and specs.

### 7.2 KG (lightweight)

- Node: `id` (artifact identity), `project_id`, `scope`, `type` (module, symbol, spec, doc), `path`, `attrs`.
- Edge: `src`, `dst`, `type` (defines, references, implements_spec, depends_on), `scope`, `attrs`.
- Keep the schema small on purpose. Resist modeling everything. Add edge types only when a recall query needs them.

### 7.3 Registry

- Project record: `project_id`, `name`, `topology`, `client_or_tenant` (for isolation), `created_at`, `last_indexed_at`, `location` (local path or central endpoint reference).
- The recall skill reads the registry, filters by isolation, then queries the matching index.

### 7.4 Scoping and promotion keys

- Every node and chunk carries `scope` and stable artifact identity.
- Promotion is an idempotent upsert from local to global keyed on identity.
- Deletions and renames across the boundary are deferred. Document the gap.

## 8. Configuration model

Generate `docs/CONFIGURATION.md` and a commented example config.

- A single project config file, for example `cartographer.toml`, committed to the repo for shared settings, with a gitignored local override for per-developer secrets and paths.
- Selects topology (local, central), backend drivers (vdb, kg, embedder), promotion trigger, isolation tenant, active stacks, and retrieval budgets.
- Secrets never in the committed file. Central endpoints and credentials come from the gitignored local override or the environment.

## 9. Security, isolation, and data governance

Generate `docs/SECURITY_AND_ISOLATION.md`. Treat this as a hard requirement, not a nicety.

- **Tenant isolation is a hard boundary.** Cross-project recall must never cross a client or tenant boundary. The registry carries a tenant key and the recall skill enforces it before any query. There is no global "all projects" index.
- **Local by default for embeddings.** Source code should not leave the machine for embedding unless a team explicitly configures an API embedder and accepts the egress.
- **Central backend is opt-in and scoped per project or per tenant.** No shared central store spans tenants.
- **Secrets** live in the gitignored local override or the environment, never in committed config or the KG or VDB.
- **What stays local, always.** Unmerged working state stays on the developer's machine. Only merged artifacts are eligible for promotion to a central store.

## 10. Constraints and assumptions

- **Cowork caveat.** Plugin hooks do not fire in Claude Code Cowork Desktop sessions today, only in the Claude Code CLI, because Cowork restricts settings resolution to user scope. Skills, commands, and MCP servers from the same plugin still work. If teams use Cowork, the always-on ingestion will not trigger there. Document this prominently.
- **PostToolUse is observe-only.** It cannot undo an edit. Use it to enqueue, not to gate.
- **Embedding cost and latency.** Never embed on every keystroke. Debounce and batch on turn or commit boundaries.
- **Squash and rebase.** Handled by keying on artifact identity, not commit SHA. True history-rewrite reconciliation is deferred.
- **Backends assumed installable locally.** The local defaults must run with no external service.

## 11. Roadmap and phasing

Generate `docs/ROADMAP.md`. Phase boundaries are firm. Do not pull deferred work forward without an explicit decision.

**Phasing principle.** When a phase closes, everything in its scope must work end to end, for real, against real state. Do not ship a feature as a stub or a placeholder and call the phase done. If a feature cannot be finished within a phase's boundary, the whole feature moves to a later phase; a partially working version of it does not count as progress.

| Phase | Scope | Exit criteria |
|---|---|---|
| Phase 1: MVP, local only | CLI `init` with detect and merge, cross-stack baseline plus Python and React packs, local VDB and KG via MCP, archaeology skill, ingest and preload and retrieve hooks, recall over local | A real session demonstrably recalls prior knowledge without the model being told to. Prove the loop. |
| Phase 2: configurable central | Central backend drivers, promotion on merge, global index, read order local then global, registry with tenant isolation | A merge promotes merged artifacts to the global index idempotently, and a second developer sees them. |
| Phase 3: sync and lifecycle | Deletions, renames, history-rewrite handling, reconciliation, conflict policy | Deferred. Design spike only until Phase 2 is stable. |

The single most important Phase 1 validation is that recall actually happens in a live session. That is the exact place these systems usually fail, so treat it as the acceptance gate for the whole approach.

The standards distribution track (Section 5.6) is phased independently of the phases above, since it is a packaging-and-authoring concern, not a KG/VDB concern:

| Phase | Scope | Exit criteria |
|---|---|---|
| Standards, local (done) | Cross-stack, python, and react packs bundled inside the CLI package; `init` and `stack add` copy from the bundled install | Implemented and verified end to end; see `cli/README.md`. Changing a standard still requires a CLI release. |
| Standards Registry and web app | A versioned, cloud-hosted index of pack content (candidate: S3 or an S3-compatible store); a separate web app for SME authoring, review, and publish; CLI fetches from the registry with bundled defaults as fallback | An SME publishes a new pack version through the web app, with no CLI release, and a project's next `cartographer stack add` picks it up. |

## 12. Success criteria

- Setup is one command and never destroys existing config.
- After ingestion, a fresh session surfaces relevant prior knowledge without the developer or the model asking for it.
- Standards are applied automatically and are contributable by PR.
- Switching from local to central is a config change, not a rewrite.
- Isolation holds: no query ever crosses a tenant boundary.

## 13. Candidate tech choices (to confirm, not to lock)

| Concern | Candidates | Lean |
|---|---|---|
| CLI language | Python, Node | Confirm with team. Python fits the data and embedding tooling. |
| Local VDB | LanceDB, Qdrant embedded | LanceDB for zero-service on-disk simplicity |
| Local KG | Kuzu embedded, SQLite triples | Kuzu for real graph queries with no service |
| Embedder | fastembed, sentence-transformers | Local default, API embedder opt-in |
| Central VDB | Qdrant, Milvus, pgvector | Team choice |
| Central KG | Neo4j, PuppyGraph | Team choice |

Record the confirmed choices as ADRs, see Section 16.

## 14. Open questions to resolve at kickoff

Put these in `docs/OPEN_QUESTIONS.md` and do not resolve them silently.

1. CLI language: Python or Node.
2. Promotion trigger default: git post-merge hook, CI on merge, or manual command.
3. Retrieval budget: how many tokens the preload and per-turn hooks may inject.
4. Spec format assumption: what a spec file looks like in the spec-driven workflow, so ingestion can anchor on it.
5. Registry location in local-only topology: per-machine or per-user-home.
6. Marketplace hosting: internal git host, path, and access model.
7. Versioning and pinning policy for standards packs.
8. Standards Registry storage: S3, an S3-compatible store (R2, MinIO), or a lightweight database-backed service.
9. Standards web app auth and review model: who can author, who can approve a pack version before it publishes.
10. CLI fallback behavior: exact conditions under which `stack add`/`init` fall back to bundled defaults versus fail loudly when a Standards Registry is configured but unreachable.

## 15. Writing conventions for all generated documents

- Human-sounding prose. No em dashes anywhere.
- Dense and tabular for technical content. Tables where they earn their place, prose otherwise.
- Concise and formal. No filler, no marketing tone.
- State assumptions inline. Where a decision is open, say so and route it to `docs/OPEN_QUESTIONS.md`.

## 16. Deliverables for this Claude Code session

Generate the following in the working directory. Documents in full prose per Section 15. Code as stubs only, with docstrings and TODOs, no business logic.

Documentation set:

```
docs/
├── README.md                     # what Cartographer is, how to install, how to use
├── ARCHITECTURE.md               # the three layers, the two-pronged model, topologies
├── DATA_MODEL.md                 # Section 7 expanded
├── CONFIGURATION.md              # Section 8 expanded, plus a commented example config
├── SECURITY_AND_ISOLATION.md     # Section 9 expanded
├── ROADMAP.md                    # Section 11 expanded
├── OPEN_QUESTIONS.md             # Section 14
├── CONTRIBUTING.md               # how to add a stack pack, how to contribute
├── components/
│   ├── cli.md
│   ├── plugin.md
│   ├── skills.md
│   ├── hooks.md
│   ├── mcp-servers.md
│   ├── standards-packs.md
│   └── standards-webapp.md       # future phase, not generated this session; see Section 6.7
├── contracts/
│   ├── vdb-tools.md              # MCP tool contracts for the VDB server
│   └── kg-tools.md               # MCP tool contracts for the KG server
└── adr/
    ├── 0000-template.md
    └── 0001-record-architecture-decisions.md
```

Repository scaffold (stubs and manifests, no logic):

```
cartographer/
├── PROJECT_BRIEF.md              # this brief, copied in for reference
├── cli/src/cartographer/runtime/ # bundled runtime assets (hooks, MCP servers, skills), per Section 6.2
├── cli/                          # real CLI implementation (init, detect, stack add, promote, recall, doctor), per Section 6.1 -- already built, see cli/README.md
├── standards/                    # cross-stack baseline plus python and react packs
├── standards-webapp/             # NOT part of this deliverable set; placeholder for the Section 6.7 / 5.6 phase
├── cartographer.example.toml     # commented example config
└── docs/                         # as above
```

Also generate:
- A top-level `README.md` that orients a new contributor in under a minute.
- ADR 0001 recording the decision to use ADRs, and a stub ADR per confirmed choice from Section 13 once the team confirms them.

When you finish, produce a short `KICKOFF_SUMMARY.md` listing what you created, every existing file you merged or would have merged, and the open questions that still block Phase 1.
