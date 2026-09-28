# Cartographer: Architecture

This document describes the three-layer architecture of Cartographer, its deployment topologies, the rule governing what work belongs in hooks versus skills versus MCP tools, and the AWS reference deployment for the central topology.

The knowledge layer (VDB and KG) stores code, specifications, and project documentation. Claude can query any of these during a session. Developers can also seed documentation explicitly via `cartographer init` or a dedicated seed command, so the knowledge base is useful from day one even before the ingestion hooks have observed any edits.

---

## 1. Layers at a glance

Cartographer has three layers. Each maps to a distinct concern and a distinct set of Claude Code primitives.

| Layer | Concern | Primary components |
|---|---|---|
| Distribution | How capability reaches a project | CLI (`cartographer`), Plugin package |
| Behavior | When and how knowledge is captured and recalled | Skills, hooks |
| State | Where knowledge lives and how it is queried | VDB driver, KG driver, registry |

The layers are designed so that the distribution layer is independent of backend choice, the behavior layer is independent of topology, and the state layer is swappable via a driver interface. A project running local-only and a project running against a central cloud backend use identical hooks and skills; the only difference is the driver configuration.

---

## 2. Component map

```
cartographer-plugin/         Plugin package, installed from git marketplace
  skills/
    archaeology/             Bootstrap a KB from an existing codebase (invoked deliberately)
    recall/                  Cross-project recall, isolation-checked (invoked deliberately)
  hooks/                     hooks.json: ingest, preload, retrieve
  mcp-servers/               VDB and KG tool servers (travel with the plugin)

cli/                         Thin CLI for per-project setup (installable via pip)
  cartographer init          Detect and merge existing config, scaffold workspace, provision index
  cartographer detect        Dry-run report of what init would change
  cartographer stack add     Apply a standards pack into the workspace
  cartographer seed          Ingest a documentation source into the local index explicitly
  cartographer promote       Manual promotion of merged artifacts to global index
  cartographer recall        Debug wrapper around the recall query flow
  cartographer ui            Lightweight local web UI to browse the VDB, KG, and registry
  cartographer doctor        Validate config, backend reachability, plugin wiring

standards/                   Cross-stack baseline plus per-stack packs
  cross-stack/
  python/
  react/

standards-webapp/            Standards web app: SME authoring, review, and publish (deferred; see Section 6 below)
```

The CLI and the plugin are complementary, not alternatives. The plugin owns reusable capability (skills, hooks, MCP servers). The CLI owns per-project setup and state provisioning. A project needs both.

---

## 3. The behavior layer: hooks versus skills versus MCP tools

This is the single most important design rule. Getting the placement wrong is how always-on recall systems fail silently.

| Capability | Mechanism | Event or invocation | Why here and not elsewhere |
|---|---|---|---|
| Bootstrap KB from existing codebase | Skill (archaeology) | User or Claude invokes once | Deliberate, one-time, needs judgment |
| Update KG and VDB on file change | Hook (PostToolUse enqueue, Stop/commit flush) | Automatic on every edit | Must be a guarantee, not a hope -- a model-invoked skill can miss a turn |
| Preload context at session start | Hook (SessionStart) | Automatic on session open | Recall must happen without the model asking |
| Per-turn retrieval | Hook (UserPromptSubmit) | Automatic on each prompt | Keeps recall fresh within a session; controls token cost |
| Deep or targeted knowledge lookup | MCP tool (vdb or kg server) | Model calls when it decides it needs more | Targeted, on-demand; supplements hook-injected context |
| Cross-project recall | Skill (recall) + MCP tool | User asks | Deliberate; needs isolation check before any query fires |

### Ingestion hook design rules

- PostToolUse fires after every Write and Edit and is observe-only. Use it as an enqueue signal only: mark files dirty, do not embed inline. Embedding inline blocks the turn.
- Flush the embed and KG update on the Stop event (turn boundary) or on a git-commit matcher. Debounce so a burst of edits produces one flush.
- Watch spec files specifically. In spec-driven projects the spec is the highest-signal artifact and the anchor for relationship edges.
- Documentation files (markdown, RST, ADRs, READMEs, wikis, runbooks) are first-class artifacts alongside code and specs. The hook watches them with the same priority.

### Documentation seeding

Developers can seed documentation into the knowledge layer explicitly, without waiting for the ingestion hook to observe edits. Two paths:

| Path | When to use |
|---|---|
| `cartographer init --seed-docs <path>` | At setup time, to ingest an existing docs directory or wiki export into the local index |
| `cartographer seed <path>` | At any time, to add or refresh a documentation source (a directory, a single file, or a glob) |

Seeded documentation is ingested by the same pipeline as hook-triggered ingestion: chunked, embedded, and upserted into the VDB and KG under `artifact_type: doc`. Claude can query it through the same recall hooks and MCP tools used for code and spec recall.

### Local knowledge browser

`cartographer ui` launches a lightweight local web server (FastAPI + single-page HTML/JS) that lets a developer visually inspect what Cartographer knows about their project. It is a developer tool for the local index -- not the Standards web app (which is a separate application for SME authoring).

| View | What it shows |
|---|---|
| Search | Semantic search over the local VDB; scored results with path, artifact type, and chunk text |
| Graph | Force-directed visualization of KG nodes and edges; click to inspect neighbors |
| Registry | All projects registered on this machine with topology and index stats |
| Stats | Chunk, node, and edge counts per artifact type; last indexed timestamp |

The UI has no build step: plain HTML, CSS, and vanilla JS served as static files from the CLI package. D3.js is loaded from CDN for the graph view and degrades gracefully to a node list when offline.

---

## 4. The state layer: driver interface

All VDB and KG operations go through a driver interface. Local and central backends implement the same contract; switching is a configuration change, not a code change.

### 4.1 VDB driver contract (minimum viable surface)

| Operation | Signature |
|---|---|
| `upsert` | `(chunks: List[Chunk], scope: Scope) -> None` |
| `query` | `(text: str, k: int, scope: Scope) -> List[ScoredChunk]` |
| `delete` | `(ids: List[str], scope: Scope) -> None` |
| `ensure_collection` | `(project_id: str, scope: Scope) -> None` |

### 4.2 KG driver contract (minimum viable surface)

| Operation | Signature |
|---|---|
| `upsert_nodes` | `(nodes: List[Node], scope: Scope) -> None` |
| `upsert_edges` | `(edges: List[Edge], scope: Scope) -> None` |
| `query` | `(pattern: str, scope: Scope) -> List[Node]` |
| `neighbors` | `(node_id: str, depth: int, scope: Scope) -> List[Node]` |
| `ensure_namespace` | `(project_id: str, scope: Scope) -> None` |

`Scope` is either `local` or `global`. Both drivers expose the same operations; scope selects which store instance they address.

### 4.3 Local and central backends

| Backend | Local (always embedded) | Central (admin-provisioned) |
|---|---|---|
| VDB | LanceDB embedded -- ships with the CLI install, on-disk in `.cartographer/local/`, no service required, not configurable | pgvector (primary). Any backend implementing the driver contract: Qdrant, Milvus, OpenSearch, Weaviate. |
| KG | Kuzu embedded -- ships with the CLI install, on-disk in `.cartographer/local/`, no service required, not configurable | Neo4j (primary). Any backend implementing the driver contract: PuppyGraph, ArangoDB. |
| Embedder | fastembed local model (no egress) -- same in both topologies by default | API embedder if the team explicitly accepts that source code leaves the machine. |

The local backends are fixed. Developers need zero local infrastructure beyond what ships with the pip install. The central backend is a configuration choice made by the team admin and applied once per project; developers receive connection details and add them to their gitignored `.cartographer.local.toml`.

---

## 5. Deployment topologies

### 5.1 Local only (default)

```
Developer machine
+------------------------------------------+
|  Claude Code session                     |
|  +---------+  +---------+  +----------+ |
|  | Skills  |  |  Hooks  |  | MCP svrs | |
|  +---------+  +---------+  +----------+ |
|       |             |            |       |
|  +------------------------------------------+
|  |     Local index (project-scoped)         |
|  |   LanceDB VDB    |    Kuzu KG            |
|  +------------------------------------------+
|  |         Registry (per-machine)           |
|  +------------------------------------------+
+------------------------------------------+
```

No central service. No promotion. No network traffic for knowledge operations.

### 5.2 Central, opt-in (multi-developer)

```
Developer A machine              Developer B machine
+---------------------+          +---------------------+
|  Local index A      |          |  Local index B      |
|  LanceDB + Kuzu     |          |  LanceDB + Kuzu     |
+---------------------+          +---------------------+
         |                                |
         |  cartographer promote          |  cartographer promote
         |  (triggered on merge)          |  (triggered on merge)
         v                                v
+--------------------------------------------------------+
|                  Central index                         |
|   VDB driver (Qdrant / pgvector / Neptune / ...)       |
|   KG driver  (Neo4j / Neptune / ArangoDB / ...)        |
|   Scoped per project; tenant-isolated                  |
+--------------------------------------------------------+
```

Read order during coding: local first (freshest, includes unmerged work), then global (merged canonical), with results tagged by origin.

Promotion is not live sync. It fires at the merge boundary. Unmerged working state never leaves the developer's machine.

---

## 6. Standards distribution

Standards packs are a separate concern from the KG/VDB topology and phased independently.

| Phase | How packs are distributed | Source of truth |
|---|---|---|
| Current (done) | Bundled inside the CLI package at `cli/src/cartographer/standards_packs/` | CLI release |
| Planned | Standards Registry: a versioned, cloud-hosted index; Standards web app for SME authoring and publishing | Registry; CLI falls back to bundled defaults when registry is unreachable |

The Standards Registry is a storage backend (S3 or an S3-compatible store). The standards web app is a separate application that writes to the registry. Both are deferred until this phase is formally scheduled.

---

## 7. AWS reference deployment

This section describes one concrete way to run the central topology on AWS. It is a reference, not a requirement. The driver interface means any compatible backend can substitute for any AWS service listed here.

### 7.1 Central knowledge index

| Concern | AWS service | Notes |
|---|---|---|
| Central VDB | Amazon Aurora PostgreSQL + pgvector | Implements the VDB driver contract. Aurora Serverless v2 scales to zero for intermittent workloads. pgvector is a driver swap from local LanceDB, not an architecture change. |
| Central KG | Neo4j (self-hosted or Neo4j Aura) | Implements the KG driver contract. Cloud-agnostic: runs on any cloud or on-premises. Neo4j Aura is the managed offering. Cypher query language. Preferred over Neptune because it is not AWS-dependent and supports local development via Docker. |
| Embedder | Runs locally on each developer machine by default | Source code does not leave the machine. An Amazon Bedrock embedder can be configured as an opt-in override for teams that accept egress. |
| Promotion trigger | AWS CodeBuild (CI step on merge to main), or a GitHub Actions workflow | Runs `cartographer promote` against the central backend after a successful merge build. |

### 7.2 Standards Registry

| Concern | AWS service | Notes |
|---|---|---|
| Pack storage | Amazon S3 | Each published pack version is an immutable object keyed by `<pack-name>/<version>/`. Versioned bucket. |
| Pack distribution | Amazon CloudFront | CDN in front of S3 for low-latency reads from CLI across regions. |
| CLI fallback | Bundled pack in the CLI package | The CLI falls back to bundled defaults when S3/CloudFront is unreachable or unconfigured. |

### 7.3 Standards web app

| Concern | AWS service | Notes |
|---|---|---|
| Compute | Amazon ECS Fargate | Containerized application, no server management. |
| Load balancing | Application Load Balancer (ALB) | Terminates TLS, routes to ECS tasks. |
| Auth | Amazon Cognito | User pools for SME authoring accounts. Cognito JWT authorizer on ALB or API Gateway. |
| Persistent state | Amazon DynamoDB or RDS | Draft state, review workflow records, published-version index. Choice pending; see open questions. |
| Pack publish writes | S3 (via service) | The web app writes immutable pack versions to the Standards Registry S3 bucket on publish approval. |

### 7.4 Networking and isolation

- Developer machines connect to the central backend over HTTPS using an API key. No VPN or VPC endpoint is required.
- Each developer or team provisions an API key via the central backend's management interface. The key is stored in the gitignored local config override or the environment, never committed to the repository.
- Tenant isolation is enforced at the application layer: every VDB and KG query carries a `project_id` and `tenant` key. No query crosses a tenant boundary. This is a hard requirement, not a best-effort.
- Secrets (API keys, database passwords, Cognito client ids) live in AWS Secrets Manager on the server side. On the client side they live in the gitignored local config override or the environment. They are never committed to the repository, never stored in the KG or VDB, and never appear in log output.

---

## 8. Data flows

### 8.1 Ingestion flow (local, per-developer)

Applies to code, specs, and documentation files equally.

```
Edit or Write tool fires (code, spec, or doc file)
  -> PostToolUse hook: mark file dirty in local queue (artifact_type: code | spec | doc)
  -> [Claude turn continues unblocked]
Turn ends (Stop event) or git commit fires
  -> Flush hook: read dirty queue
  -> Extract artifacts and relationships from changed files
  -> Embed text chunks with local embedder
  -> VDB driver: upsert chunks to local scope (artifact_type preserved)
  -> KG driver: upsert nodes and edges to local scope
  -> Clear dirty queue

Developer seeds documentation explicitly (cartographer seed <path>)
  -> Same pipeline from "Extract artifacts" onward
  -> artifact_type: doc for all seeded files
```

### 8.2 Recall flow (local, per-turn)

```
Developer submits a prompt
  -> UserPromptSubmit hook fires
  -> KG driver: query local scope for relevant nodes given prompt context
  -> VDB driver: query local scope for top-k relevant chunks
  -> [If central topology configured] repeat queries against global scope
  -> Tag results by origin (local or global)
  -> Inject budgeted results into prompt context
  -> Claude receives prompt with knowledge context prepended
```

### 8.3 Promotion flow (central topology only)

```
Branch merges to main
  -> Promotion trigger fires (CI step or post-merge hook)
  -> cartographer promote runs against merged artifacts
  -> VDB driver: upsert chunks to global scope (idempotent, keyed by artifact identity)
  -> KG driver: upsert nodes and edges to global scope (idempotent)
  -> Other developers' next session sees promoted artifacts via global scope read
```

Promotion is idempotent. Nodes and chunks are keyed by artifact identity (file path plus symbol, or spec id), not by commit SHA. Squash merges are safe.

---

## 9. What is not in scope

The following are explicitly deferred and must not be pulled forward without a formal phase decision.

| Deferred concern | Why deferred | Where it lands |
|---|---|---|
| True bidirectional sync between local and global | Design complexity; keying on artifact identity keeps the deferral cheap | Phase 3 |
| Deletion and rename reconciliation across the promotion boundary | Requires a tombstone protocol; deferred until Phase 2 is stable | Phase 3 |
| Cross-tenant query | Hard isolation requirement; violating it is a security issue, not a feature | Never |
| Real-time embedding via an API embedder by default | Egress risk for client code; requires explicit opt-in | Config-gated |
| Hooks in Claude Code Cowork Desktop sessions | Cowork restricts settings resolution to user scope; plugin hooks do not fire | Platform limitation; document prominently |

---

*For open questions that still block Phase 1, see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). For phase exit criteria, see [ROADMAP.md](ROADMAP.md).*
