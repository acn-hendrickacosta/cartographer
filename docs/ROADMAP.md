# Cartographer: Roadmap

This document defines the phased delivery plan for Cartographer. Phase boundaries are firm. Do not pull deferred work forward without an explicit decision recorded here.

---

## Phasing principle

When a phase closes, everything in its scope must work end to end, for real, against real state. A feature that cannot be finished within a phase's boundary moves to a later phase in full -- a partially working version does not count as progress and does not close the phase. Stubs, placeholders, and "mostly done" features are not acceptable phase exits.

---

## Phase 1: MVP, local only

**Goal:** Prove the recall loop. A developer installs Cartographer, works in a Claude Code session, and relevant prior knowledge surfaces automatically without them asking for it. The system works reliably, end to end, on a real project.

### Scope

| Component | What ships |
|---|---|
| CLI | `init`, `detect`, `stack add`, `seed`, `promote` (no-op in local-only), `recall`, `doctor` |
| Local knowledge browser | `cartographer ui` -- FastAPI local web server with search, graph, registry, and stats views |
| Standards packs | Cross-stack baseline, Python pack, React pack -- bundled in CLI |
| Plugin | Plugin package structure, `hooks.json`, MCP server definitions wired in |
| Hooks | `ingest` (enqueue + flush), `preload` (SessionStart), `retrieve` (UserPromptSubmit) |
| MCP servers | VDB server (LanceDB driver), KG server (Kuzu driver) |
| Skills | `archaeology` skill, `recall` skill |
| Ingestion pipeline | Code, spec, and plain-text doc ingestion; chunking; local fastembed embedder |
| Registry | Per-machine SQLite registry |

### What is explicitly out of scope for Phase 1

- Central backend drivers (Qdrant, pgvector, Neo4j, Neptune, etc.)
- Promotion to a global index
- Binary document extraction (`.docx`, `.pptx`, `.pdf`) -- plain text formats only
- Standards Registry and Standards web app
- Multi-developer shared knowledge

### Exit criteria

All of the following must be demonstrated against a real project, not a synthetic test:

| Criterion | How to verify |
|---|---|
| `cartographer init` completes without errors on a greenfield project and on an existing project with Claude config | Run both; confirm no existing config is overwritten |
| `cartographer init` on an existing project merges additively and backs up what it would overwrite | Inspect `.claude/settings.json`, `CLAUDE.md`, `.mcp.json` before and after |
| The cross-stack baseline and Python pack are written into `.claude/standards/` | Inspect directory |
| A new Claude Code session starts and the preload hook injects context from the local index | Observe the session context block in the first turn |
| After editing a file, the ingest hook updates the local VDB and KG by end of turn | Query with `cartographer recall` immediately after the turn ends |
| A fresh session (simulating "next day") surfaces knowledge from a prior session's ingested artifacts | Start a new session; confirm the preload context includes artifacts from the prior session |
| `cartographer recall "<query>"` returns ranked results with origin tags | Run against a seeded project |
| `cartographer seed <docs-path>` ingests a directory of markdown files into the local index | Seed, then query; confirm results reference the seeded content |
| `cartographer doctor` passes all checks on a correctly initialized project | Run and confirm exit code `0` |
| The recall skill returns cross-project results and blocks cross-tenant queries | Test with two projects, same tenant (should return) and different tenants (should block) |
| `cartographer ui` starts, opens a browser, and shows seeded content in the search view | Run `cartographer ui`; search for a term from a seeded doc; confirm scored results appear |

**The single most important exit criterion:** a developer working in a real Claude Code session can ask a question about prior work and Claude answers using recalled knowledge it was not explicitly told about in the current session. This must be demonstrated live, not mocked.

---

## Phase 2: Configurable central

**Status:** Code complete as of 2026-09-29. Exit criteria walkthrough pending — requires a provisioned central backend (pgvector + Neo4j) and two developer machines. Do not mark this phase closed until the two-developer walkthrough in `docs/runbooks/two-developer-walkthrough.md` is completed and all 10 exit criteria are recorded.

**Goal:** A second developer joins a project. After a branch merges, they see the first developer's merged knowledge in their session, through the global index.

### Scope

| Component | What ships |
|---|---|
| Central VDB drivers | At least one: pgvector (recommended first), Qdrant |
| Central KG drivers | At least one: Neo4j (recommended first) |
| Promotion pipeline | `cartographer promote` writes to global scope; CI trigger documented |
| Global index read order | Local-first, then global; results tagged by origin |
| Central backend API key auth | Per-developer keys, configured in local override |
| `cartographer doctor` central checks | Verify central backend reachability and API key validity |

### What is explicitly out of scope for Phase 2

- Deletion and rename reconciliation across the promotion boundary
- Rebase and history-rewrite handling
- Standards Registry and web app
- Binary document extraction

### Exit criteria

| Criterion | How to verify |
|---|---|
| Developer A initializes a project with central topology and promotes after a merge | Run `cartographer promote --dry-run` first, then promote; inspect global collection stats |
| Developer B initializes the same project on a different machine with their own API key | `cartographer doctor` passes on Developer B's machine |
| After Developer A promotes, Developer B's next session preloads from both local and global scope | Observe origin tags in the preload context block |
| A VDB query returns local-first results with global fallback; results are tagged by origin | Run `cartographer recall --scope both` and verify tags |
| Tenant isolation holds: a cross-tenant recall query is blocked | Test with two projects on different tenants |
| Promotion is idempotent: running `cartographer promote` twice produces the same global state | Promote, inspect stats, promote again, inspect stats again -- counts must match |

---

## Phase 3: Sync and lifecycle

**Goal:** Handle the gaps that were deferred in Phase 2 — deletions, renames, rebases, and conflict resolution when local and global indexes diverge.

**Design spike status:** Complete. All four protocol documents are written in `docs/phases/phase-3-protocols/`. Implementation is broken into four sequential passes.

### Sub-phases

| Pass | Document | Scope | Entry condition |
|---|---|---|---|
| 3.1 | [phase-3.1-watcher-local-cleanup.md](phases/phase-3.1-watcher-local-cleanup.md) | Watcher `on_deleted` / `on_moved` — local index real-time cleanup | Phase 2 code complete. No central backend needed. |
| 3.1.1 | [phase-3.1.1-management-server.md](phases/phase-3.1.1-management-server.md) | Management server — `POST /api/ingest` in serve; `seed` delegates when serve is running | Phase 3.1 complete. |
| 3.1.2 | [phase-3.1.2-ui-read-delegation.md](phases/phase-3.1.2-ui-read-delegation.md) | `POST /api/query` and `/api/neighbors` in KG server; `cartographer ui` delegates reads when serve is running | Phase 3.1.1 complete. |
| 3.2 | [phase-3.2-tombstone.md](phases/phase-3.2-tombstone.md) | Tombstone protocol — global index deletion at promote time + `cartographer gc` | Phase 3.1 complete. Central backend required. |
| 3.3 | [phase-3.3-rename-tracking.md](phases/phase-3.3-rename-tracking.md) | Rename tracking — `supersedes` edges, git rename detection, recall redirect | Phase 3.2 complete. |
| 3.4 | [phase-3.4-conflict-resolution.md](phases/phase-3.4-conflict-resolution.md) | Conflict resolution — `⚠ CONFLICT` notice in recall context | Phase 3.3 complete (soft dependency). |

### Entry condition

Phase 3 does not start until Phase 2 is stable in production use.

### Exit criteria

See each sub-phase document for detailed criteria. Phase 3 is complete when all four sub-phases pass and the Phase 2 two-developer walkthrough passes without regression.

---

## Standards distribution track

This track runs independently of the phases above. It is a packaging and authoring concern, not a KG/VDB concern.

| Phase | Scope | Status | Exit criteria |
|---|---|---|---|
| Standards, local | Cross-stack, Python, and React packs bundled in the CLI; `init` and `stack add` copy from bundled install | Done | Implemented and verified end to end. Changing a standard requires a CLI release. |
| Standards Registry and web app | Versioned cloud-hosted index (S3); separate web app for SME authoring, review, and publish; CLI fetches from registry with bundled fallback | Not started | An SME publishes a new pack version through the web app with no CLI release, and a project's next `cartographer stack add` picks it up. |

The Standards Registry and web app phase does not have a start date. It begins when OQ-08 (registry storage), OQ-09 (auth and review model), and OQ-10 (CLI fallback behavior) are resolved. See [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).

---

## What "done" means for every phase

A phase is done when:

1. Every item in its scope list is implemented and tested against real state.
2. Every exit criterion is demonstrated and recorded.
3. The open questions that were blocking the phase are closed and documented.
4. The next phase's open questions have been reviewed and any new ones identified.
5. This roadmap document is updated to reflect the phase's actual completion date and any scope changes made during implementation.

A phase is not done because the code compiles, tests pass, or a demo works on a clean machine. It is done when a real developer can use it on a real project and the exit criteria hold.

---

*For the open questions that block each phase, see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). For architecture decisions made during implementation, see the ADRs in [adr/](adr/).*
