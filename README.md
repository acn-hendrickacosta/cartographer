# Cartographer

Cartographer gives any Claude Code project a persistent knowledge layer: a local knowledge graph and vector index that are kept current automatically as code and specs change, and that Claude consults automatically while working. It ships with a comprehensive standards index — 12 language and framework packs, 57 auto-loading skills, and 44 specialized review agents — and installs in one command into a new or existing project.

---

## The problem it solves

Claude Code loses context between sessions. It re-reads files it has already understood, forgets decisions from earlier sessions, and has no durable model of how a codebase and its specifications relate. Asking Claude to "remember" something is not a guarantee — reliability for always-on behavior requires deterministic hooks, not prompting.

Cartographer wires those hooks. Knowledge is captured on every edit and injected at every session start and every prompt turn, without the developer or Claude having to ask.

---

## How it works

Three layers:

1. **CLI** (`cartographer`) — sets up the workspace, provisions the local index, and manages standards packs. Run once at project start; idempotent after that.
2. **Plugin** — skills and hooks that travel with the project. Hooks ingest changes automatically; skills handle deliberate, judgment-heavy operations like indexing an existing codebase or cross-project recall.
3. **State layer** — a local vector database (LanceDB) and knowledge graph (Kuzu), provisioned per project, with an opt-in upgrade path to a shared central backend for multi-developer teams.

---

## Quick start

### Install the CLI

Cartographer is not yet published to PyPI. Install directly from GitHub:

```bash
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

### Initialize a project

```bash
cd my-project
cartographer init --stack python
```

This detects and merges any existing Claude Code configuration, then installs the full standards set into your workspace. The resulting directory structure:

```
.claude/
  standards/
    cross-stack/           ← 28 universal standards files, always in context
    python/                ← 11 Python-specific standards files
  skills/
    api-design/
      SKILL.md             ← auto-loaded when designing REST endpoints
    tdd-workflow/
      SKILL.md             ← auto-loaded when writing tests
    python-patterns/
      SKILL.md             ← auto-loaded for Python idioms
    python-testing/
      SKILL.md             ← auto-loaded for pytest questions
    …21 skills total for a python stack, each in its own subdirectory
  agents/
    code-reviewer.md       ← general code review agent
    python-reviewer.md     ← Python-specific reviewer
    django-reviewer.md     ← Django-specific reviewer
    architect.md
    security-reviewer.md
    …22 agents total for a python stack
CLAUDE.md                  ← merged with any existing content
.claude/settings.json      ← hooks wired (PostToolUse, Stop, SessionStart, UserPromptSubmit)
.mcp.json                  ← cartographer-vdb and cartographer-kg MCP servers
cartographer.toml          ← project config (committed)
.cartographer.local.toml   ← per-developer secrets (gitignored)
.cartographer/local/       ← local LanceDB + Kuzu index (gitignored)
```

**How skills auto-load:** Each `SKILL.md` file contains a `description` frontmatter field. Claude Code reads all descriptions at session start and loads a skill automatically when the task it is being asked to do matches the description. No `/command` invocation is needed, though you can also call any skill explicitly via `/skill-name`.

**How agents are invoked:** Agent files in `.claude/agents/` define specialist subagents Claude can spawn during a session. Claude may invoke them proactively, or you can direct it to: "use the security-reviewer agent to audit this route."

**What hooks do automatically:**
- `PostToolUse` (Write|Edit|MultiEdit) → `cartographer hook enqueue` — queues changed files for reingestion
- `Stop` → `cartographer hook flush` — flushes the queue into the local VDB and KG at end of session
- `SessionStart` → `cartographer hook preload` — injects prior session context at startup
- `UserPromptSubmit` → `cartographer hook retrieve` — retrieves relevant VDB context on every prompt

### Add a stack pack later

```bash
cartographer stack add typescript
cartographer stack add golang
```

Each `stack add` installs the stack's standards into `.claude/standards/<stack>/`, its skills into `.claude/skills/<skill-name>/SKILL.md`, and its agents into `.claude/agents/<agent-name>.md`. The core set (cross-stack standards + 15 core skills + 18 core agents) is also installed if not already present. All operations are idempotent: re-running installs only files that changed.

### Seed existing documentation and code

Do a first full index pass after `init`. This populates the VDB and knowledge graph so Claude has something to query.

```bash
cartographer seed .          # index the whole project
cartographer seed docs/      # index a documentation directory only
cartographer seed docs/spec.md  # index a single file
```

Supported formats: `.md`, `.rst`, `.txt`, `.adoc`, `.docx`, `.pptx`, `.pdf`, and source files for all supported languages. Binary formats (`.docx`, `.pptx`, `.pdf`) require a running Claude Code session for extraction; they are skipped with a warning when run from a plain terminal.

Add `--enrich` to extract LLM-derived semantic relationships (`implements_spec`, `depends_on`) in addition to structural ones. This is slower (~30–60 s per file) and requires `claude` on PATH, so consider running it on a subset first.

### Index an existing codebase

Open a Claude Code session in the project and run:

```
/archaeology
```

Bootstraps the knowledge base from the existing codebase and documentation in one pass. After it completes, the ingest hooks maintain the index incrementally on every edit.

### Start the servers

`cartographer serve` is the long-running process that keeps everything working. It starts two local MCP servers — one for the vector database, one for the knowledge graph — and a background filesystem watcher that re-indexes changed files automatically.

```bash
cartographer serve                              # VDB on :4010, KG on :4011, watcher on
cartographer serve --vdb-port 4020 --kg-port 4021  # custom ports
cartographer serve --no-watch                   # MCP servers only, no background re-indexing
```

Keep this running in a background terminal while you work. Claude Code connects to it via the two MCP server entries that `cartographer init` writes to `.mcp.json`.

**Why the watcher matters:** Claude Code hooks only fire on Claude's own tool calls. A `git pull`, a branch switch, or an edit from another tool never triggers a hook, so the index would silently drift stale. The watcher uses OS-level filesystem events to catch every change, regardless of how it happened or whether hooks are allowed by your organization's Claude Code policy. Running `cartographer serve` with the watcher on (the default) is what actually keeps the index current.

### Browse the knowledge layer

```bash
cartographer ui                  # opens a browser at http://127.0.0.1:7341
cartographer ui --port 8080      # use a different port
cartographer ui --no-browser     # print the URL instead of opening a tab
```

Requires the `ui` extra. Install it with:

```bash
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[ui]"
```

The UI has five views:

| View | What it does |
|---|---|
| **Search** | Live semantic search as you type, filterable by artifact type (Doc / Code / Spec). Each result has a relevance bar and a truncate/expand toggle. Click any result to jump to its graph neighborhood. |
| **Browse** | A collapsible file-tree of all module, doc, and spec nodes in the knowledge graph — a second way in when you don't know what to search for. Has its own filter box that auto-expands matching branches. |
| **Graph** | Pan/zoom interactive graph. Drag nodes, click a node to open its detail panel and drill down into its neighborhood. Hover any edge to see its relationship type. A legend explains every node color and edge type. |
| **Registry** | Every project registered on this machine, with the currently-open one highlighted. |
| **Stats** | Chunk and node counts by type for the current project's local index, shown as proportional bars. |

The UI shows your **local** index only. It does not query a central or shared index.

### Verify the setup

```bash
cartographer doctor
```

Reports the health of the config, local backends, hook wiring, installed packs, and (for `central` topology) whether the remote VDB and KG backends are reachable. Run this first whenever something seems off.

---

## Command reference

| Command | What it does |
|---|---|
| `cartographer init [--stack <name>] [--topology central]` | Scaffold the workspace: write `CLAUDE.md`, wire hooks into `.claude/settings.json`, write `.mcp.json`, provision the local VDB and KG, and apply the baseline standards pack. Idempotent — safe to re-run. |
| `cartographer seed <path> [--enrich] [--no-recursive]` | Index a file or directory into the local VDB and KG. Run once after `init`; the serve watcher keeps things current after that. |
| `cartographer stack add <name>` | Install a language standards pack (standards files, skills, agents) into the workspace. |
| `cartographer serve [--vdb-port N] [--kg-port N] [--no-watch]` | Start the VDB and KG MCP servers and the background filesystem watcher. Keep this running while you work. |
| `cartographer ui [--port N] [--no-browser]` | Open the local knowledge browser at `http://127.0.0.1:7341`. |
| `cartographer doctor` | Validate the installation end to end: config, local backends, hook wiring, installed packs, and (if central) remote backend connectivity. |
| `cartographer detect` | Read-only preview of what `init` would create or merge. Safe to run before committing to `init`. |
| `cartographer recall <query> [--k N]` | Query the local KG and VDB directly from the terminal and print matches. Useful for confirming that specific content is indexed. |
| `cartographer promote [--full] [--dry-run]` | Push local index changes to the shared central index (central topology only). |

---

## Standards index

Cartographer ships a comprehensive standards index derived from curated community sources and refined for tool-agnostic use. All content is developer-facing guidance — no AI-tooling boilerplate, no vendor lock-in. Standards are stored as Markdown files and read by Claude as persistent passive reference throughout every session.

### Pack overview

| Pack | Standards | Skills | Agents |
|---|---|---|---|
| `cross-stack` | 28 files | 15 core skills | 18 core agents |
| `python` | 11 files | 6 stack skills + 15 core | 4 stack agents + 18 core |
| `typescript` | 9 files | 4 stack skills + 15 core | 1 stack agent + 18 core |
| `react` | 9 files | 5 stack skills + 15 core | 2 stack agents + 18 core |
| `golang` | 7 files | 2 stack skills + 15 core | 2 stack agents + 18 core |
| `rust` | 6 files | 2 stack skills + 15 core | 2 stack agents + 18 core |
| `java` | 8 files | 8 stack skills + 15 core | 2 stack agents + 18 core |
| `kotlin` | 7 files | 6 stack skills + 15 core | 2 stack agents + 18 core |
| `angular` | 4 files | 1 stack skill + 15 core | 18 core only |
| `vue` | 6 files | 2 stack skills + 15 core | 1 stack agent + 18 core |
| `swift` | 7 files | 4 stack skills + 15 core | 2 stack agents + 18 core |
| `dart` | 6 files | 2 stack skills + 15 core | 2 stack agents + 18 core |

---

## Cross-stack standards

Installed to `.claude/standards/cross-stack/` with every pack. These apply to all projects regardless of language or framework.

| File | What it covers |
|---|---|
| `accessibility.md` | WCAG 2.2 Level AA compliance across the POUR principles — semantic HTML, contrast ratios, keyboard navigation, focus management, touch target sizes, ARIA labels, and accessible modal patterns |
| `api-design.md` | REST API conventions: resource naming, HTTP method semantics, status codes, filtering and pagination via query params, error envelopes, versioning strategy, and rate limiting |
| `architecture-decision-records.md` | How to capture significant decisions as numbered ADR files in `docs/adr/` using the Nygard format with context, alternatives considered, and consequences |
| `architecture-patterns.md` | Hexagonal Architecture (Ports and Adapters): domain isolation, port interfaces, inbound/outbound adapters, dependency direction, and composition root wiring |
| `backend-patterns.md` | Backend API structure, repository/service layer separation, database access patterns (N+1 avoidance, column selection), and cross-cutting middleware design |
| `build-failure-resolution.md` | Incremental build failure resolution: reading errors fully, fixing in dependency order, verifying after each fix, and escalation criteria for unresolvable failures |
| `claude-code-usage.md` | Responsible Claude Code usage norms — preferring edits over scaffolding, reading before editing, surfacing assumptions, and treating generated artifacts as human-facing communication |
| `code-review.md` | Seven-dimension code review process that prioritizes correctness first, requires concrete failure scenarios for every finding, and avoids speculative generalization requests |
| `coding-style.md` | Clean code principles: KISS, DRY, YAGNI, immutability preference, file and function size limits, and meaningful naming conventions |
| `containerization.md` | Docker best practices: multi-stage builds, pinned image tags, non-root runtime users, HEALTHCHECK instructions, `.dockerignore`, and layer cache optimization |
| `contract-first-design.md` | Defining one authoritative machine-checkable contract (OpenAPI, AsyncAPI, Protocol Buffers, or JSON Schema) before writing implementation when teams or services work in parallel |
| `database-migrations.md` | Forward-only, immutable migrations with schema/data separation, pre-production testing against production-sized data, and a safety checklist for each migration |
| `deployment.md` | Rolling, blue-green, and canary deployment strategies; CI/CD pipeline stages from lint through production deploy; guidance on when to use each strategy |
| `design-systems.md` | Maintaining a single source of truth for visual language using design tokens, controlled component variants, minimal API surfaces, and ten-dimension consistency audits |
| `e2e-testing.md` | E2E testing with Page Object Model, stable locators (`data-testid` and ARIA roles), condition-based waiting instead of arbitrary sleeps, and CI retry configuration |
| `error-handling.md` | Typed error hierarchies, Result types for expected failures, consistent API error envelopes, and strict separation of user-facing messages from internal developer context |
| `feature-development.md` | Structured feature workflow: discovery, research/reuse, codebase exploration, and architecture design — all required before writing implementation code |
| `frontend-patterns.md` | Frontend component design: composition over inheritance, compound components with context, custom hooks for data fetching, and scoped state management |
| `git-hygiene.md` | Small reviewable commits, why-focused commit messages, Conventional Commits format, no-force-push policy on shared branches, and team-appropriate branching strategies |
| `kubernetes.md` | Kubernetes workload best practices: pinned image tags, resource requests/limits, RollingUpdate strategy, `terminationGracePeriodSeconds`, and all three probe types (liveness, readiness, startup) |
| `mcp-server-patterns.md` | MCP server design patterns for tools, resources, and prompts — with typed input schemas, transport selection by client context, and single-responsibility primitives |
| `postgresql.md` | PostgreSQL index type selection by query pattern (B-tree, GIN, BRIN), query optimization, and schema best practices for production databases |
| `production-readiness.md` | Multi-dimension production readiness audit — security, authentication, observability, and failure recovery — required before launches and major releases |
| `redis.md` | Redis data structure selection by use case (strings, hashes, sorted sets, HyperLogLog) and operational best practices for caching, sessions, queues, and leaderboards |
| `security-baseline.md` | Input validation at system boundaries, secrets management (never commit credentials), and injection attack prevention for SQL, shell, and HTML contexts |
| `spec-driven-workflow.md` | Treating specs as the authoritative artifact — requiring a spec before implementation, and reconciling any spec/code disagreement as a bug regardless of which side is "right" |
| `tdd.md` | Red-Green-Refactor TDD cycle requiring tests written before implementation, a valid compiling RED state before coding, and minimum implementation to pass each failing test |
| `testing.md` | 80%+ combined test coverage across unit, integration, and E2E tests, with TDD order enforced and all three test types required for every codebase |

---

## Core skills

Installed to `.claude/skills/<name>/SKILL.md` with every pack. Claude reads each skill's `description` frontmatter at session start and loads the skill automatically when a task matches. Skills are also invokable explicitly as `/<skill-name>`.

| Skill | Installed as | Auto-loads when… |
|---|---|---|
| `api-design` | `.claude/skills/api-design/SKILL.md` | Designing or reviewing REST endpoints, resource names, status codes, pagination, or versioning |
| `architecture-decision-records` | `.claude/skills/architecture-decision-records/SKILL.md` | The user says "record this decision" or "ADR this", or discusses trade-offs between frameworks or databases |
| `tdd-workflow` | `.claude/skills/tdd-workflow/SKILL.md` | Writing a new feature, fixing a bug, refactoring, or when told to write failing tests first |
| `error-handling` | `.claude/skills/error-handling/SKILL.md` | Designing error types, retries, circuit breakers, or user-facing failure messages in TypeScript, Python, or Go |
| `e2e-testing` | `.claude/skills/e2e-testing/SKILL.md` | Writing Playwright tests, structuring page objects, or fixing flaky E2E runs in CI |
| `git-workflow` | `.claude/skills/git-workflow/SKILL.md` | Committing, branching, reviewing PRs, tidying local commits before merging, or resolving conflicts |
| `security-review` | `.claude/skills/security-review/SKILL.md` | Adding authentication, handling user input, working with secrets, creating API endpoints, or implementing payment/sensitive features |
| `production-audit` | `.claude/skills/production-audit/SKILL.md` | Pre-launch reviews, post-merge checks, or "what breaks in prod?" questions |
| `deployment-patterns` | `.claude/skills/deployment-patterns/SKILL.md` | Setting up CI/CD, containerizing an app, or checking production readiness before a release |
| `containerization` | `.claude/skills/containerization/SKILL.md` | Creating or reviewing Dockerfiles and Compose services, or planning local development environments |
| `database-migrations` | `.claude/skills/database-migrations/SKILL.md` | Adding or modifying database migrations in PostgreSQL, Prisma, Drizzle, Django, or golang-migrate |
| `accessibility` | `.claude/skills/accessibility/SKILL.md` | Building or reviewing UI components, forms, modals, dropdowns, or fixing a11y lint findings |
| `architecture-patterns` | `.claude/skills/architecture-patterns/SKILL.md` | Applying Hexagonal Architecture, designing domain boundaries, or inverting dependencies across TypeScript, Java, Kotlin, and Go |
| `contract-first` | `.claude/skills/contract-first/SKILL.md` | Designing API contracts or schemas, coordinating frontend/backend or service-to-service work |
| `backend-patterns` | `.claude/skills/backend-patterns/SKILL.md` | Building or reviewing Node.js, Express, or Next.js API routes and their data access layers |

---

## Core agents

Installed to `.claude/agents/<name>.md` with every pack. Available throughout every session as specialist subagents.

| Agent | Role | When to use |
|---|---|---|
| `code-reviewer` | Expert code review with CRITICAL/HIGH/MEDIUM/LOW severity triage | Immediately after writing or modifying any code |
| `architect` | System design, scalability, and technical decision-making | Planning new features, refactoring large systems, or making architectural decisions |
| `security-reviewer` | OWASP Top 10, secrets detection, vulnerability patterns | Before any code goes to production or when handling sensitive data |
| `performance-optimizer` | Profiling, rendering, Web Vitals, N+1 queries, memory leaks | When users report slowness or builds show large bundles |
| `code-explorer` | Codebase analysis — entry points, execution paths, data flow | Onboarding to a codebase or before major refactoring |
| `code-simplifier` | Reduces complexity, removes duplication, improves clarity without changing behavior | Cleaning up a module after a sprint or before a PR |
| `database-reviewer` | PostgreSQL schema design, query optimization, indexing, and Row Level Security | Reviewing database migrations, schemas, or complex queries |
| `tdd-guide` | Red-Green-Refactor cycle enforcement, test quality coaching | Implementing new features or fixing bugs test-first |
| `a11y-architect` | WCAG 2.2 compliance audit, platform accessibility strategy, accessibility ADRs | Building or reviewing UI components for accessibility |
| `refactor-cleaner` | Dead code detection, unused exports, orphaned files via static analysis | Safe removal of code that is no longer needed |
| `planner` | Detailed phased implementation plans with task breakdown, sizing, and risk assessment | Before any non-trivial implementation to align on approach |
| `doc-updater` | Keeps inline docs, README files, and codemaps accurate and synchronized | After significant code changes that affect documented behavior |
| `silent-failure-hunter` | Finds empty catch blocks, swallowed errors, dangerous fallbacks, missing error propagation | Security audits and pre-release reviews |
| `pr-test-analyzer` | Reviews new code for behavioral test coverage gaps, rates test quality | PR review when test coverage is in question |
| `build-error-resolver` | TypeScript and build error resolution with minimal diffs | When the build is broken |
| `e2e-runner` | Playwright-based end-to-end test execution and debugging | Writing, running, and debugging E2E tests for critical user journeys |
| `comment-analyzer` | Evaluates accuracy, completeness, and maintainability of inline comments and JSDoc | Flagging misleading, redundant, or stale comments |
| `type-design-analyzer` | TypeScript type definition evaluation — encapsulation, invariant enforcement, expressiveness | Assessing whether type definitions are expressive, correct, and maintainable |

---

## Stack-specific standards, skills, and agents

### Python (`cartographer stack add python`)

**Standards** installed to `.claude/standards/python/`:

| File | What it covers |
|---|---|
| `async.md` | Guidelines for choosing async I/O, avoiding mixed sync/async call stacks, and using `asyncio.gather` for concurrent operations |
| `dependencies.md` | Declaring and pinning project dependencies in `pyproject.toml`, separating optional extras from required ones |
| `django-testing.md` | pytest-django setup, test-specific settings (SQLite, fast hashers, eager Celery), and migration handling for Django test suites |
| `django.md` | Django project structure, split-settings organization (base/development/production/test), and environment-based configuration |
| `error-handling.md` | Raising specific exception types with clear messages, avoiding broad catches except at process boundaries, and writing custom exception classes |
| `fastapi.md` | FastAPI app factory pattern, project structure, and testability configuration for production applications |
| `patterns.md` | Pythonic idioms: EAFP, context managers for resource management, and readability-first naming conventions |
| `security.md` | SQL injection prevention via parameterized queries, subprocess safety, and file path validation against directory traversal |
| `style-and-testing.md` | Python version targeting, type hints on public signatures, and dependency economy |
| `testing.md` | pytest conventions for file/function/class naming, single-behavior test functions, and test isolation via fixtures |
| `type-hints.md` | Type annotation requirements on all public signatures, forward reference handling with `__future__` annotations, and built-in generic type preferences |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `python-patterns` | Writing or reviewing Python code and idiomatic structure, typing, or PEP 8 is in question |
| `python-testing` | Writing pytest tests — fixtures, mocks, parametrization, or coverage |
| `fastapi-patterns` | Building or reviewing FastAPI apps — Pydantic schemas, dependencies, async handlers, auth, or tests |
| `django-patterns` | Building or reviewing Django apps, DRF APIs, ORM queries, or caching |
| `django-security` | Reviewing Django authentication, authorization, input handling, or deployment settings |
| `django-tdd` | Writing Django or DRF tests with pytest-django, or driving a Django feature test-first |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `python-reviewer` | PEP 8 compliance, Pythonic idioms, type hints, security, and performance. MUST BE USED for Python projects |
| `django-reviewer` | ORM correctness, DRF patterns, migration safety, security misconfigurations, and production-grade Django practices |
| `fastapi-reviewer` | Async correctness, dependency injection, Pydantic schemas, security, OpenAPI quality, and testing |
| `django-build-resolver` | pip/Poetry errors, migration conflicts, import errors, Django configuration issues, and collectstatic failures |

---

### TypeScript (`cartographer stack add typescript`)

**Standards** installed to `.claude/standards/typescript/`:

| File | What it covers |
|---|---|
| `backend-patterns.md` | RESTful API design conventions and Node.js backend architectural patterns for TypeScript services |
| `code-review.md` | Severity-grouped checklist (critical security through minor style) for reviewing TypeScript and JavaScript code |
| `coding-style.md` | Type and interface annotation guidelines, where to annotate vs. infer, and TypeScript style conventions |
| `nestjs.md` | NestJS project structure, feature module organization, and placement of cross-cutting concerns |
| `nextjs.md` | Next.js 16+ Turbopack incremental bundling, faster dev startup, and its behavior as the new default bundler |
| `patterns.md` | API response envelope patterns and idiomatic TypeScript architectural idioms |
| `prisma.md` | Prisma schema design, ID strategy selection (cuid/uuid vs. autoincrement), and ORM query patterns |
| `security.md` | Secret management via environment variables and TypeScript-specific security practices |
| `tooling.md` | Vite build tool behavior — specifically the type-checking gap between `vite build` and `tsc`, and CI requirements to close it |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `nestjs-patterns` | Building or reviewing a NestJS backend — modules, providers, DTO validation, guards, or interceptors |
| `nextjs-patterns` | Developing or debugging Next.js 16+ apps, diagnosing slow dev startup or hot reload, choosing between bundlers, or reviewing middleware/proxy file naming |
| `prisma-patterns` | Writing a Prisma schema or query, or debugging transactions, migrations, or serverless connection limits |
| `vite-patterns` | Working with `vite.config.ts`, Vite plugins, or Vite-based projects |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `typescript-reviewer` | Type safety, async correctness, Node/web security, and idiomatic patterns. MUST BE USED for TypeScript/JavaScript projects |

---

### React (`cartographer stack add react`)

**Standards** installed to `.claude/standards/react/`:

| File | What it covers |
|---|---|
| `accessibility.md` | Semantic HTML element selection, ARIA attribute usage, and accessibility region patterns for React applications |
| `code-review.md` | React-specific review concerns including security, hook usage, and component correctness |
| `component-design.md` | Controlled vs. uncontrolled component choices, hook-based behavior composition, and JSX render organization |
| `data-fetching.md` | Hook-based data fetching patterns, explicit loading/error/empty state handling, and `AbortController` cleanup |
| `performance.md` | Measurement-first optimization approach, correct usage of `React.memo` and `useMemo`, and avoiding premature optimization |
| `react-native.md` | Production React Native patterns with Expo including Expo Router, the New Architecture, and managed workflow conventions |
| `security.md` | `dangerouslySetInnerHTML` as a security-critical code review point and XSS prevention in React |
| `state-management.md` | Progression from local `useState` to global state libraries, Context use cases, and library selection guidance |
| `style-and-testing.md` | TypeScript requirements, PascalCase/camelCase/`use`-prefix naming conventions, and one-component-per-file organization |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `react-patterns` | Writing or reviewing React components — hooks discipline, server/client component boundaries, Suspense, form actions |
| `react-testing` | Writing or fixing tests for React components, hooks, or pages |
| `react-performance` | Writing, reviewing, or refactoring React/Next.js code for performance |
| `react-native-patterns` | Building or editing React Native/Expo screens, components, navigation, or data layers |
| `frontend-a11y` | Building or reviewing forms, modals, dropdowns, tooltips, or tabs; fixing a11y lint or code-review findings |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `react-reviewer` | Hook correctness, render performance, server/client component boundaries, accessibility, and React-specific security. MUST BE USED for React projects |
| `react-build-resolver` | React build failures across Vite, webpack, Next.js, CRA, Parcel, esbuild, and Bun — JSX/TSX compile errors, hydration mismatches, bundler-specific configuration |

---

### Go (`cartographer stack add golang`)

**Standards** installed to `.claude/standards/golang/`:

| File | What it covers |
|---|---|
| `build.md` | Go build verification commands, common compilation errors, and module dependency hygiene |
| `code-review.md` | Security-first review checklist covering injection attacks, error handling, concurrency, and API design |
| `coding-style.md` | Idiomatic Go style: formatting, error wrapping, interface design, naming, and package conventions |
| `patterns.md` | Reusable Go design patterns: functional options, repository abstraction, and other idiomatic constructs |
| `security.md` | Secret management, SQL injection prevention, command injection, and TLS configuration for Go applications |
| `testing.md` | Go testing standards: TDD approach, table-driven tests, race detection, and coverage targets by code category |
| `tooling.md` | Required Go tooling: `go fmt`, `go vet`, `staticcheck`, `golangci-lint`, and benchmarking in CI |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `golang-patterns` | Writing or reviewing Go code and idiomatic structure or conventions are in question |
| `golang-testing` | Writing Go tests — table-driven cases, subtests, benchmarks, fuzzing, or coverage |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `go-reviewer` | Idiomatic Go, concurrency patterns, error handling, and performance. MUST BE USED for Go projects |
| `go-build-resolver` | Go build errors, `go vet` issues, and linter warnings with minimal changes |

---

### Rust (`cartographer stack add rust`)

**Standards** installed to `.claude/standards/rust/`:

| File | What it covers |
|---|---|
| `code-review.md` | Safety-first review checklist covering `unsafe` usage, ownership, error handling, and idiomatic patterns |
| `coding-style.md` | `rustfmt` and Clippy-enforced formatting, linting, and stylistic conventions for idiomatic Rust |
| `patterns.md` | Reusable Rust design patterns including repository abstraction with swappable concrete implementations behind traits |
| `security.md` | Secrets management and prevention of common vulnerabilities in Rust applications |
| `testing.md` | Rust testing organization: unit tests in `cfg(test)` modules following TDD methodology |
| `tooling.md` | `cargo fmt`, Clippy, and static analysis enforcement in CI |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `rust-patterns` | Writing or reviewing Rust code and ownership, error handling, traits, or concurrency is in question |
| `rust-testing` | Writing Rust tests — unit, integration, async, property-based, or coverage |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `rust-reviewer` | Ownership, lifetimes, error handling, `unsafe` usage, and idiomatic patterns. MUST BE USED for Rust projects |
| `rust-build-resolver` | `cargo build` errors, borrow checker issues, and `Cargo.toml` problems with minimal changes |

---

### Java (`cartographer stack add java`)

**Standards** installed to `.claude/standards/java/`:

| File | What it covers |
|---|---|
| `code-review.md` | Prioritized checklist of critical, major, and minor review criteria for Java (Spring Boot and Quarkus) code |
| `coding-style.md` | `google-java-format` enforcement, immutability, naming conventions, and idiomatic patterns for Java 17+ |
| `jpa-persistence.md` | JPA entity design, explicit indexing, auditing fields, lazy fetch strategy, and transaction management |
| `patterns.md` | Three-layer architecture, constructor injection, and record-based DTO mapping patterns for Java services |
| `quarkus.md` | CDI scope usage, Jakarta REST endpoint design, and JWT-based security patterns for Quarkus applications |
| `security.md` | Secret management via environment variables, SQL injection prevention, and input validation for Java services |
| `springboot.md` | Thin-controller, layered-service, and data access patterns for production-grade Spring Boot REST applications |
| `testing.md` | JUnit 5, AssertJ, and Mockito testing by layer: unit, web (MockMvc), integration, and persistence (Testcontainers) |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `java-standards` | Writing or reviewing Java in a Spring Boot or Quarkus service — naming, immutability, Optional, streams, CDI |
| `springboot-patterns` | Building or reviewing a Spring Boot backend — REST layer, services, data access, caching, or async work |
| `springboot-security` | Reviewing Spring Security authn/authz, validation, CSRF, secrets, headers, or rate limiting |
| `springboot-tdd` | Adding features, fixing bugs, or refactoring Spring Boot code test-first |
| `quarkus-patterns` | Building or reviewing a Quarkus service, especially with Camel messaging or Panache data access |
| `quarkus-security` | Adding authentication/authorization, validating input, managing secrets, or hardening a Quarkus application |
| `quarkus-tdd` | Adding features, fixing bugs, or refactoring event-driven Quarkus services |
| `jpa-patterns` | Designing JPA entities or relationships, or fixing a Hibernate query, transaction, or N+1 problem |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `java-reviewer` | Layered architecture, JPA/Panache, MongoDB, security, and concurrency — auto-detects Spring Boot or Quarkus. MUST BE USED for all Java code changes |
| `java-build-resolver` | Maven/Gradle build errors, Java compiler errors — auto-detects and applies framework-specific fixes |

---

### Kotlin (`cartographer stack add kotlin`)

**Standards** installed to `.claude/standards/kotlin/`:

| File | What it covers |
|---|---|
| `android-architecture.md` | Module structure, strict dependency rules, and UseCase/Repository patterns for Android Clean Architecture |
| `code-review.md` | Prioritized review checklist covering domain module purity, coroutine safety, and architectural violations |
| `coroutines.md` | Structured concurrency, scope selection, parallel decomposition, and Flow usage in Kotlin coroutines |
| `database.md` | HikariCP configuration, Flyway migration, and Exposed ORM table definition standards for Kotlin database access |
| `ktor.md` | Application module structure, route grouping, and authentication patterns for Ktor server applications |
| `patterns.md` | Idiomatic Kotlin: `val` preference, data/value/sealed class usage, and null safety |
| `testing.md` | Kotest spec styles, custom matchers, and MockK for unit and suspend-function testing |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `kotlin-patterns` | Writing or reviewing Kotlin code and idiomatic structure or null safety is in question |
| `kotlin-testing` | Writing Kotlin tests with Kotest or MockK, or testing coroutines and checking coverage |
| `coroutines-flows` | Writing coroutines or Flow code on Android or KMP, or debugging cancellation and concurrency |
| `android-architecture` | Structuring modules, layers, or data flow in an Android or KMP project |
| `exposed-patterns` | Working with the Exposed ORM — DSL or DAO queries, transactions, pooling, or migrations |
| `ktor-patterns` | Building a Ktor server — routing, plugins, auth, DI, serialization, or tests |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `kotlin-reviewer` | Idiomatic patterns, coroutine safety, Compose best practices, clean architecture violations, and Android pitfalls |
| `kotlin-build-resolver` | Kotlin/Gradle build errors, Kotlin compiler errors, and Gradle issues with minimal changes |

---

### Angular (`cartographer stack add angular`)

**Standards** installed to `.claude/standards/angular/`:

| File | What it covers |
|---|---|
| `coding-style.md` | Standalone components with OnPush change detection, `inject()`-based DI, and Angular CLI version currency |
| `patterns.md` | Smart/dumb component split, service-owned data access, and signal-based reactive async patterns with `takeUntilDestroyed` |
| `security.md` | Prohibits `bypassSecurityTrust*` calls, mandates HttpClient interceptors for auth tokens, SSR and route-guard security |
| `testing.md` | TestBed configuration for standalone components, signal input testing via `setInput`, and CDK harness usage |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `angular-patterns` | Creating Angular projects, components, or services; best practices on reactivity (signals, `linkedSignal`, `resource`), forms, DI, routing, SSR, accessibility, animations, styling, testing, or CLI tooling |

**Agents:** Core agents only (18 agents from cross-stack).

---

### Vue (`cartographer stack add vue`)

**Standards** installed to `.claude/standards/vue/`:

| File | What it covers |
|---|---|
| `code-review.md` | Block-approval checklist covering `v-html` XSS vectors, Nuxt `runtimeConfig` secret leaks, missing API input validation, and prop destructuring reactivity bugs |
| `coding-style.md` | `<script setup lang="ts">`, SFC block order, PascalCase file naming, Prettier + `eslint-plugin-vue`, and pure computed getters |
| `nuxt.md` | SSR-safe rendering rules for Nuxt 4 — hydration-safe data fetching, browser-only code guards, and stable `useAsyncData` keys |
| `patterns.md` | Container/presentational component split, composable design with `MaybeRefOrGetter` + `toValue()`, and cleanup in `onUnmounted` |
| `security.md` | Prevents `v-html` XSS, URL scheme injection, runtime template compilation from user input, and mandates `httpOnly` cookies over localStorage for tokens |
| `testing.md` | Vitest + `@vue/test-utils` + happy-dom stack, `mount` vs `shallowMount` guidance, and async assertion patterns with `flushPromises` |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `vue-patterns` | Building or reviewing Vue 3, Nuxt, or Pinia code — Composition API, reactivity, or router navigation |
| `nuxt-patterns` | Building or reviewing a Nuxt 4 app, or debugging hydration mismatches and SSR-safe data fetching |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `vue-reviewer` | Composition API correctness, reactivity pitfalls, component architecture, template security, and Vue-specific performance |

---

### Swift (`cartographer stack add swift`)

**Standards** installed to `.claude/standards/swift/`:

| File | What it covers |
|---|---|
| `code-review.md` | Critical block-approval checklist: force unwrap, `try!`, force cast, hardcoded secrets, `UserDefaults` misuse, and global ATS bypass |
| `coding-style.md` | SwiftFormat + SwiftLint enforcement, `let`-over-`var` default, struct-first value semantics, typed throws, `Sendable` conformance, and structured concurrency |
| `concurrency.md` | Swift 6.2 Approachable Concurrency — single-threaded by default, `@MainActor` for shared state, and isolated conformances for actor-bound protocol conformance |
| `patterns.md` | Small focused protocols per external concern, `Sendable` protocol requirements for actor boundaries, and protocol extensions for default implementations |
| `security.md` | Keychain for all sensitive data, ATS enforcement, certificate pinning for high-security endpoints, URL scheme validation, and parameterized SQL |
| `swiftui.md` | `@Observable` for all new view models replacing `ObservableObject`/`@Published`, with correct `@State` ownership and `@Bindable` for two-way binding |
| `testing.md` | Swift Testing framework with `@Test` functions and `#expect` assertions for richer, expression-capturing failure output |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `swiftui-patterns` | Building or reviewing SwiftUI views, `@Observable` state, navigation, or render performance |
| `swift-concurrency` | Adopting Swift 6.2 concurrency — offloading with `@concurrent` or resolving main-actor isolation |
| `swift-protocol-di` | Swift code needs testing and file system, network, or external APIs must be mocked via focused protocols |
| `swift-actor-persistence` | Persisting data in Swift and a data race or thread-safety problem needs designing out |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `swift-reviewer` | Protocol-oriented design, value semantics, ARC memory management, Swift Concurrency, and idiomatic patterns. MUST BE USED for Swift projects |
| `swift-build-resolver` | Swift/Xcode build failures, SPM dependency issues, and code signing problems with minimal changes |

---

### Dart/Flutter (`cartographer stack add dart`)

**Standards** installed to `.claude/standards/dart/`:

| File | What it covers |
|---|---|
| `code-review.md` | Critical block-approval checklist: business logic in widgets, bang operator misuse, bare catch clauses, hardcoded secrets, and unencrypted sensitive storage |
| `coding-style.md` | `dart format` enforcement in CI, `final`/`const` preference, Dart naming conventions, and null-aware operators over bang operator |
| `flutter-patterns.md` | Separate `StatelessWidget`/`ConsumerWidget` classes over builder methods, `const` constructors everywhere, and narrowly scoped rebuild strategies |
| `patterns.md` | Clean Architecture layering (domain/data/presentation) with repository interfaces defined in domain using domain model types |
| `security.md` | `flutter_secure_storage` for runtime secrets, HTTPS-only enforcement, complete logout clearing, and parameterized SQL queries |
| `testing.md` | Test type taxonomy (unit/widget/golden/integration), `bloc_test` for BLoC/Cubit state sequences, and `tearDown` stream leak prevention |

**Skills** installed to `.claude/skills/<name>/SKILL.md`:

| Skill | Auto-loads when… |
|---|---|
| `flutter-patterns` | Writing or reviewing Dart and Flutter code — state, widgets, navigation, networking, or architecture |
| `flutter-code-review` | Reviewing Flutter or Dart code, whatever state management library the project uses |

**Agents** installed to `.claude/agents/`:

| Agent | Focus |
|---|---|
| `flutter-reviewer` | Widget best practices, state management patterns (BLoC, Riverpod, Provider, GetX, MobX, Signals), Dart idioms, performance, accessibility, and clean architecture. Library-agnostic |
| `dart-build-resolver` | `dart analyze` errors, Flutter compilation failures, pub dependency conflicts, and `build_runner` issues |

---

## Agents for additional languages

The following agents are installed when specific language agents packs are bundled alongside packs that depend on them. They review code written in languages without a full standards pack.

| Agent | Language | Focus |
|---|---|---|
| `cpp-reviewer` | C++ | Memory safety, modern C++ idioms, concurrency, and performance |
| `cpp-build-resolver` | C++ | CMake, compilation error resolution, and linker issues |
| `csharp-reviewer` | C# | .NET conventions, async patterns, security, nullable reference types, and performance |
| `php-reviewer` | PHP | PSR-12 compliance, PHP type system, Eloquent ORM patterns, security, and performance |
| `fsharp-reviewer` | F# | Functional idioms, type safety, pattern matching, computation expressions, and performance |

---

## Repository structure

```
cartographer/
  cli/                               Python CLI package (pip-installable)
    src/cartographer/
      commands/
        init.py                        cartographer init — workspace setup, hooks, MCP, baseline pack
        stack.py                       cartographer stack add — installs standards + skills + agents
        seed.py                        cartographer seed — bulk document ingestion
        serve.py                       cartographer serve — starts VDB and KG MCP servers
        doctor.py                      cartographer doctor — health checks
      standards_packs/               Standards files installed to .claude/standards/
        cross-stack/                   28 universal standards files (always installed)
        python/                        11 Python standards files
        typescript/                    9 TypeScript standards files
        react/                         9 React standards files
        golang/                        7 Go standards files
        rust/                          6 Rust standards files
        java/                          8 Java standards files
        kotlin/                        7 Kotlin standards files
        angular/                       4 Angular standards files
        vue/                           6 Vue standards files
        swift/                         7 Swift standards files
        dart/                          6 Dart standards files
      skills_packs/                  Skills installed to .claude/skills/<name>/SKILL.md
        core/                          15 skills installed with any stack
        python/                        6 Python-specific skills
        typescript/                    4 TypeScript-specific skills
        react/                         5 React-specific skills
        golang/                        2 Go-specific skills
        rust/                          2 Rust-specific skills
        java/                          8 Java-specific skills
        kotlin/                        6 Kotlin-specific skills
        angular/                       1 Angular-specific skill
        vue/                           2 Vue-specific skills
        swift/                         4 Swift-specific skills
        dart/                          2 Dart-specific skills
      agents_packs/                  Agents installed to .claude/agents/
        core/                          18 agents installed with any stack
        python/                        4 Python-specific agents
        typescript/                    1 TypeScript-specific agent
        react/                         2 React-specific agents
        golang/                        2 Go-specific agents
        rust/                          2 Rust-specific agents
        java/                          2 Java-specific agents
        kotlin/                        2 Kotlin-specific agents
        vue/                           1 Vue-specific agent
        swift/                         2 Swift-specific agents
        dart/                          2 Dart-specific agents
        cpp/                           2 C++ agents
        csharp/                        1 C# agent
        php/                           1 PHP agent
        fsharp/                        1 F# agent
      indexing/
        vdb.py                         LanceDB vector store driver
        kg.py                          Kuzu knowledge graph driver
      ingestion/
        parsers.py                     File format parser registry
      runtime/                       Plugin skills (archaeology + recall)
      ui/                            Local knowledge browser (cartographer ui)
  cartographer-plugin/               Claude Code plugin
    skills/
      archaeology/SKILL.md           /archaeology — bootstraps KG+VDB from existing codebase
      recall/SKILL.md                /recall — cross-project retrieval
    hooks/                           PostToolUse, Stop, SessionStart, UserPromptSubmit scripts
    mcp/                             MCP server definitions for VDB and KG tools
  standards/                         Source standards (pre-CLI era reference, superseded by packs)
  standards-webapp/                  Standards web app: SME authoring and publishing (deferred)
  docs/                              Full documentation set
  cartographer.example.toml          Annotated example configuration
```

---

## How skills and agents are installed

**Skills** follow the Claude Code native format:

```
.claude/skills/
  api-design/
    SKILL.md        ← frontmatter: name, description, tools. Body: instruction set.
  tdd-workflow/
    SKILL.md
  python-patterns/
    SKILL.md
  …
```

Each `SKILL.md` has a `description` field in its frontmatter. Claude reads all descriptions at session start and loads the skill automatically when the task matches. Skills can also be invoked as `/api-design`, `/tdd-workflow`, etc.

**Agents** follow the Claude Code agent format:

```
.claude/agents/
  code-reviewer.md    ← frontmatter: name, description, tools, model. Body: system prompt.
  architect.md
  python-reviewer.md
  …
```

Each agent is a specialist subagent with its own system prompt, tool list, and optionally a dedicated model. Claude can invoke them proactively or on direction.

**Idempotency:** All install functions compare file content before writing. Re-running `cartographer init` or `stack add` writes only files that changed. Legacy files in `.claude/commands/` left by older Cartographer versions are removed automatically when the corresponding skill is installed to `.claude/skills/`.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Step-by-step installation for macOS and Windows |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System layers, topologies, AWS reference deployment |
| [docs/APPLICATION_ARCHITECTURE.md](docs/APPLICATION_ARCHITECTURE.md) | CLI command flows, web app screen flows, hook runtime flows |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | VDB, KG, and registry schemas; artifact identity; promotion mechanics |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every config knob, the two-file model, environment variable overrides |
| [docs/SECURITY_AND_ISOLATION.md](docs/SECURITY_AND_ISOLATION.md) | Tenant isolation, data egress rules, secret handling |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases, scope, and exit criteria |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Decisions still open; what blocks each phase |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to add a stack pack, skill, or agent to the index |
| [docs/phases/phase-1-mvp-local.md](docs/phases/phase-1-mvp-local.md) | Phase 1 implementation plan: scope, build order, exit criteria, test approach |
| [docs/phases/phase-2-central.md](docs/phases/phase-2-central.md) | Phase 2: central backends, promotion, multi-developer |
| [docs/phases/phase-3-sync-lifecycle.md](docs/phases/phase-3-sync-lifecycle.md) | Phase 3: deletions, renames, conflict resolution |
| [docs/phases/standards-registry.md](docs/phases/standards-registry.md) | Standards Registry and web app implementation plan |
| [docs/components/cli.md](docs/components/cli.md) | CLI component spec: all commands, inputs, outputs, failure modes |
| [docs/components/standards-webapp.md](docs/components/standards-webapp.md) | Standards web app spec: roles, lifecycle, screen inventory, AWS infrastructure |
| [docs/components/hooks.md](docs/components/hooks.md) | Hook contracts, portability rules, failure handling |
| [docs/components/mcp-servers.md](docs/components/mcp-servers.md) | MCP server definitions, driver interface, authorization matrix |
| [docs/components/skills.md](docs/components/skills.md) | Archaeology and recall skill specs |
| [docs/contracts/vdb-tools.md](docs/contracts/vdb-tools.md) | VDB MCP tool contracts |
| [docs/contracts/kg-tools.md](docs/contracts/kg-tools.md) | KG MCP tool contracts |

---

## Configuration

Copy `cartographer.example.toml` to `cartographer.toml` in the project root and edit as needed. The example file is fully annotated with every available knob.

Per-developer secrets and endpoint overrides go in `.cartographer.local.toml`, which is gitignored by `cartographer init` automatically. Never put API keys in `cartographer.toml`.

For the full configuration reference, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Topologies

| Topology | When to use | Setup |
|---|---|---|
| Local only (default) | Solo developer or small team not ready for shared infra | `cartographer init` — no extra config needed |
| Central, opt-in | Multi-developer project wanting shared knowledge after merges | Set `topology.mode = "central"` and configure central VDB and KG endpoints in `.cartographer.local.toml` |

In local-only topology, the VDB and KG run entirely on-disk on the developer's machine (LanceDB and Kuzu). No service, no network, no cloud account required.

---

## Multi-developer setup

For teams using the central topology:

1. Provision a central VDB backend (pgvector on Aurora, Qdrant, or any supported driver) and a central KG backend (Neo4j, Neptune, or any supported driver).
2. Issue each developer their own API key for the central backends.
3. Each developer sets `topology.mode = "central"` in `cartographer.toml` and their API keys in `.cartographer.local.toml`.
4. Configure the promotion trigger. The recommended path is a CI step that runs `cartographer promote` on merge to main.

After a branch merges and promotion runs, all developers see the merged knowledge in their next session.

---

## Known limitations

| Limitation | Detail |
|---|---|
| Hooks do not fire in Claude Code Cowork Desktop | Cowork restricts project-scope settings. The always-on ingest, preload, and retrieve hooks are not triggered. Skills and MCP servers still work. Run `cartographer seed` manually and use `/recall` explicitly when working in Cowork. |
| Binary document extraction requires a Claude Code session | `.docx`, `.pptx`, and `.pdf` files are extracted using local Claude via MCP. Running `cartographer seed` from a plain terminal outside a Claude Code session skips binary files with a warning. |
| `cartographer ui` graph view requires internet access for D3.js | The graph view loads D3.js from CDN. In offline environments it degrades to a node list. The search, registry, and stats views work fully offline. |
| Deletions and renames are not reconciled across the promotion boundary | Stale artifacts remain in the global index until Phase 3. |

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## License

Internal use. Open to contribution — see license file for details.
