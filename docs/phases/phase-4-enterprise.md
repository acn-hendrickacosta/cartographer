# Phase 4: Enterprise Scale

**Alignment check (2026-10-05):** reviewed against the codebase after Phase 3.1–3.4 landed. All doc cross-references (ARCHITECTURE.md, DATA_MODEL.md, phase-2-central.md, phase-3-sync-lifecycle.md, ADR 0007) still resolve, and `kg_server.py`'s current tools/routes (`kg_query`, `kg_neighbors`, `kg_stats`, `/health`, `/api/ingest`, `/api/query`, `/api/neighbors`) are exactly what this doc assumes for slotting in `kg_impact`/`kg_search`. Fixed two filename typos (`.cartographer.local.toml` → `cartographer.local.toml`, no leading dot) and added four notes below, at the sections they affect, flagging places where Phase 3 work this doc predates needs to be reconciled with before implementing:

1. **Edge taxonomy governance** — the `[kg]` TOML section this proposes would collide in name with an already-existing, already-dead `[kg]` section in `cartographer.example.toml`.
2. **CI/CD freshness integration** — `promote --diff` needs to coexist with Phase 3.3's `last_promoted_sha`-based rename detection, not duplicate it.
3. **Graph versioning** — `registry.ProjectRecord` already has a `last_promoted_sha` field (Phase 3.3, single-value, a different purpose than the proposed `PromotionRecord` history).
4. **`kg_impact`** — its draft Cypher hits a known Kuzu binder limitation if ever run against local scope.

## Goal

Make Cartographer usable at org-scale: multiple teams sharing a central backend, graphs that stay fresh without manual intervention, cross-project impact analysis, and governed relationship taxonomies. After Phase 4, a platform team can deploy Cartographer once and onboard dozens of engineering teams without each team managing their own indexing infrastructure.

**Entry condition:** Phase 3 is complete and stable. The tombstone, rename, and conflict resolution protocols are in production use on at least one real project. Phase 4 must not start until Phase 3 has demonstrated reliable global index accuracy over a full release cycle.

---

## References

| Document | What to read |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Sections 4-7: central topology, scope model |
| [DATA_MODEL.md](../DATA_MODEL.md) | Sections 5-6: scoping rules, artifact identity |
| [phase-2-central.md](phase-2-central.md) | Phase 2: global index foundation this phase extends |
| [phase-3-sync-lifecycle.md](phase-3-sync-lifecycle.md) | Phase 3: lifecycle guarantees this phase depends on |
| [adr/0007-tree-sitter-for-ast-extraction.md](../adr/0007-tree-sitter-for-ast-extraction.md) | AST parser layer: calls/imports/extends edges this phase queries |

---

## What Phase 2 already provides (do not re-implement)

| Capability | Where it lives |
|---|---|
| `project_id` and `scope` on every node and edge | KG schema, VDB schema |
| `tenant` isolation field | `cartographer.toml` → `[isolation].tenant` |
| Global scope read/write protection | Promotion token, `SCOPE_WRITE_FORBIDDEN` |
| Cross-project node sharing via global scope | Promotion pipeline |
| `kg_neighbors` with scope filter | KG MCP server |

Phase 4 builds on these — it does not replace them.

---

## Scope

### In scope

| Feature | What ships |
|---|---|
| Team-layer RBAC | Read/write access control at the team and project level on the central backend |
| CI/CD freshness integration | `cartographer seed --diff` for incremental re-indexing; CI template for post-merge promotion |
| Graph versioning | `graph@<commit-sha>` pointers so queries are reproducible against a known index state |
| Cross-project impact tool | `kg_impact` MCP tool: given a node, return everything that transitively depends on it across all projects |
| Edge taxonomy governance | Canonical edge type registry; lint at seed time; schema drift detection |
| `kg_search` (NL→Cypher) | Natural-language query tool that translates to Cypher internally; agents don't need to write raw Cypher |
| Federated read with global overlays | Local graphs link to global nodes; cross-repo queries without merging all projects into one graph |
| `cartographer doctor` enterprise checks | RBAC token valid; CI integration configured; taxonomy version matches server (appends to the existing check list — `doctor.py` already reports local-VDB/KG health, central reachability, MCP wiring, parser installs, and a `serve` liveness check added in Phase 3.2.1) |

### Explicitly out of scope

- Real-time bidirectional sync (non-goal per ARCHITECTURE.md)
- Cross-tenant data sharing (never in scope)
- Standards Registry and web app (independent track)
- Binary document extraction (deferred from Phase 1, separate track)

---

## Component breakdown

### 1. Team-layer RBAC

**Context:** Phase 2 has `tenant` isolation (one tenant = one org). Phase 4 adds a team layer within a tenant so teams can have private project graphs while sharing read-only global nodes (design system specs, platform APIs, shared standards).

**What ships:**

- **Access model**: three principals — org admin, team member, read-only viewer. Three resource types — project graph (private to team), team graph (shared within team), global overlay (read-only for all).
- **Token model**: admin issues team tokens scoped to a set of `project_id`s. Token stored in `cartographer.local.toml` alongside the central backend credentials. Token is validated by the MCP servers on every tool call.
- **Enforcement point**: both VDB and KG MCP servers validate the team token before returning results. A query to `project_id` the token is not scoped to returns `PERMISSION_DENIED`, not an empty result.
- **Global overlay**: nodes seeded to `scope="global"` are readable by all tokens in the same tenant. Write to global scope still requires the promotion token from Phase 2.
- **Admin CLI**: `cartographer admin token issue --project <id> --team <name>` (admin only). `cartographer admin token revoke`. Tokens stored in a `carto_tokens` table on the central backend.

**Design spike required:** token schema, token storage location (central backend vs. separate auth service), and token validation latency budget. Spike document in `docs/phases/phase-4-protocols/rbac-token-protocol.md` before implementation.

---

### 2. CI/CD freshness integration

**Context:** `cartographer seed` today is manual. At enterprise scale, the global index drifts from main within hours of a merge. Engineers lose trust in recalled results.

**What ships:**

**`cartographer seed --diff <base-ref>`**:
- Compute the list of files changed between `<base-ref>` and `HEAD` using `git diff --name-only`
- Ingest only the changed files; skip unchanged files entirely
- Idempotent: re-running on the same diff is safe
- Exit code: `0` = success, `1` = partial failure (some files errored), `2` = config error

**`cartographer promote --diff <base-ref>`**:
- Same diff logic applied to the promotion pipeline
- Only promotes artifacts changed since `<base-ref>` to global scope

> **Reconcile with Phase 3.3 before implementing:** `promote.py` already uses git diffing — `registry.ProjectRecord.last_promoted_sha` drives `git diff --name-status --diff-filter=R {last_promoted_sha}..HEAD` for rename detection (see `phase-3.3-rename-tracking.md`). `--diff <base-ref>` as drafted here would be a second, independent git-diff mechanism computing a different file list for a different purpose (which files to promote, vs. which files were renamed). Decide whether `--diff` should reuse `last_promoted_sha` as its default base-ref (likely — "changed since last promote" is already the concept `--incremental` embodies via timestamps) rather than introducing a second, parallel notion of "the baseline to diff against."

**CI template** (GitHub Actions, GitLab CI):
- Provided as `docs/ci-templates/github-actions.yml` and `docs/ci-templates/gitlab-ci.yml`
- Runs on push to main: `cartographer seed --diff origin/main~1 && cartographer promote --diff origin/main~1`
- Requires `CARTO_CENTRAL_VDB_*` and `CARTO_CENTRAL_KG_*` env vars (same as local override, but sourced from CI secrets)

**Graph versioning** (`graph@<commit-sha>`):
- On each successful promote, write a `PromotionRecord` to the registry: `{ project_id, commit_sha, promoted_at, node_count, edge_count }`
- `kg_query` accepts an optional `at_commit` parameter; if supplied, filters to nodes promoted at or before that commit
- `cartographer log` command: lists promotion history for a project

> **Note:** `registry.ProjectRecord` already has a `last_promoted_sha` field (Phase 3.3) — but it is a single value overwritten on every promote, used as the diff base for rename detection, not a history. `PromotionRecord` needs to be a genuinely separate, append-only list (one entry per promote), not a repurposing of `last_promoted_sha` — conflating the two would break rename detection's "diff since the last promote" semantics the moment `cartographer log`/`at_commit` needs to look further back than the most recent promote.

---

### 3. Cross-project impact tool (`kg_impact`)

**Context:** The AST parser (Phase 1 extension) already emits `calls`, `imports`, and `extends` edges within a project. Phase 2 promotion pushes these to the global index. `kg_impact` traverses them across project boundaries.

**New MCP tool** (add to KG server):

```python
@mcp.tool()
def kg_impact(
    node_id: str,
    workspace: str = "",
    max_depth: int = 4,
    edge_types: str = "calls,imports,extends",
    scope: str = "global",
) -> str:
    """Return all artifacts that transitively depend on the given node.

    Use this to answer: "what breaks if I change this function/class/module?"
    Traverses calls, imports, and extends edges in reverse (callers of callee,
    importers of module, subclasses of class).

    Args:
        node_id: The artifact node id (usually file path or file::symbol).
        workspace: Absolute path to project root. Always pass this (see CLAUDE.md).
        max_depth: Maximum traversal depth 1-4 (default 4).
        edge_types: Comma-separated edge types to traverse in reverse.
        scope: "global" to traverse across all promoted projects (default), "local" for this project only.
    """
```

**Implementation**: reverse traversal Cypher query:
```cypher
MATCH p=(dependent:Artifact)-[:RelatesTo*1..{depth}]->(target:Artifact {id: $node_id})
WHERE ALL(r IN relationships(p) WHERE r.type IN $edge_types)
RETURN DISTINCT dependent.path AS path, dependent.project_id AS project_id,
       dependent.type AS type, length(p) AS distance
ORDER BY distance
```

**Output**: JSON list of `{ path, project_id, type, distance }` — which files in which projects depend on the target node, sorted by distance (direct dependents first).

> **Missing tombstone filter:** the draft query above has no `tombstoned_at` check on `dependent`. Phase 3.2 established the convention that traversal excludes tombstoned nodes — `Neo4jDriver.neighbors()` filters `(n.tombstoned_at IS NULL OR n.tombstoned_at = '')`. Without the same filter here, `kg_impact` would report a deleted file as still depending on the target, which is exactly the kind of stale-impact-report this tool exists to prevent.

> **Kuzu caveat if `scope="local"`:** this query is fine as written against Neo4j (the default, `scope="global"` path). But `kg.py`'s existing `neighbors()` function hit a real Kuzu binder limitation with this exact shape — a `$param` referenced inside an `ALL(...)` predicate over a variable-length path pattern triggers a `KU_UNREACHABLE` assertion in Kuzu's query binder. `neighbors()` works around it by validating the value and inlining it as a string literal instead of a bound parameter (see the comment at `kg.py:neighbors()`). If `kg_impact` is ever invoked with `scope="local"` against the local Kuzu KG, `$edge_types` inside `ALL(...)` needs the same literal-inlining treatment, not a bound parameter.

---

### 4. Edge taxonomy governance

**Context:** The AST parser emits `calls`, `imports`, `extends`, `defines`. The LLM enricher emits `implements_spec`, `depends_on`, and free-form `relationships`. At org scale, schema drift across projects makes cross-project Cypher queries unreliable.

**What ships:**

**Canonical edge taxonomy** (`docs/standards/edge-taxonomy.md`):
- Versioned list of allowed edge types with definitions, source (AST vs. LLM), and cardinality
- Current canonical types: `defines`, `calls`, `imports`, `extends`, `implements_spec`, `depends_on`, `relates_to`, `supersedes` (Phase 3)
- New types require a PR to `edge-taxonomy.md` and a version bump

**Lint step in `cartographer seed`**:
- After graph extraction, validate all emitted edge types against the installed taxonomy version
- Unknown edge types: log warning + skip (not error, to avoid blocking ingestion on taxonomy lag)
- `--strict` flag: fail on unknown edge types (for use in CI)

**Taxonomy version pinning** in `cartographer.toml`:
```toml
[kg]
taxonomy_version = "1.0"
```
- `cartographer doctor` validates that the project's pinned taxonomy version matches the server's current version
- Schema drift: `doctor` reports which edge types the project uses that are not in the server taxonomy

> **`[kg]` section name is already taken, and not in a good way.** `cartographer.example.toml` has a top-level `[kg]` section today (`driver = "kuzu"`) that `config.py`'s `load_config` never actually reads — it only parses `[backends.kg]`. That section has been dead documentation since before Phase 3 (same class of bug as `[recall]` vs. the real `[retrieval]`, found and partially fixed during Phase 3.4). Writing `taxonomy_version` into a bare `[kg]` section would be silently ignored exactly the same way, unless `config.py` is given a real place to parse it from. Before implementing: either extend `CentralSection`/`BackendsSection.kg` properly, or pick a section name that isn't already a stale no-op (e.g. `[kg_governance]`), and fix or remove the existing dead `[kg]`/`[vdb]`/`[embedder]`/`[ingestion]` sections in `cartographer.example.toml` while at it — they have the identical problem independent of Phase 4.

**`cartographer taxonomy list`** command: prints the current canonical edge types and their definitions.

---

### 5. `kg_search` — natural language to Cypher

**Context:** `kg_query` requires the agent to write raw Cypher. This is a barrier for agents that aren't tuned to the KG schema, and it means query quality depends on how well CLAUDE.md documents the schema.

**New MCP tool** (add to KG server):

```python
@mcp.tool()
def kg_search(
    question: str,
    workspace: str = "",
    scope: str = "local",
) -> str:
    """Answer a structural question about the codebase using the knowledge graph.

    Translates the question to Cypher internally — you do not need to write Cypher.
    Use this when kg_query would require you to know the exact schema.

    Examples:
      "What calls _build_prompt?"
      "Which files import cartographer.config?"
      "What classes extend BaseCommand?"
      "What would break if I remove area_validator.py?"

    Args:
        question: Natural language question about code structure.
        workspace: Absolute path to project root. Always pass this (see CLAUDE.md).
        scope: "local" or "global".
    """
```

**Implementation approach:**
- Send the question + KG schema description to a Claude API call (internal, not recursive over MCP)
- Claude returns a Cypher query
- Execute the Cypher query and return results
- Cap at 3 retries if the generated Cypher fails to parse

**Dependency:** requires `anthropic` Python SDK as a new optional dep (`pip install cartographer[kg-search]`). The tool returns a graceful error if the dep is missing.

**Design constraint:** the Claude call is a direct API call using the key in `cartographer.local.toml`, not a recursive MCP call. This avoids the deadlock pattern documented in the MCP server implementation notes.

---

### 6. Federated read with global overlays

**Context:** Phase 2 has a single global scope shared across projects. At org scale, teams want selective federation: "show me this team's private graph plus the org's shared design system, but not other teams' private graphs."

**What ships:**

- **Overlay configuration** in `cartographer.toml`:
  ```toml
  [kg]
  global_overlays = ["design-system", "platform-api"]  # project_ids whose global scope is readable
  ```
  Same `[kg]`-is-dead-today caveat as the taxonomy section above applies here — resolve once, consistently, for both fields.
- **`kg_impact` federation — implemented (2026-10-05)**: `Neo4jDriver.find_impact()` takes `project_ids`; `kg_server.py`'s `kg_impact` tool always passes `[cfg.project.id, *cfg.federation.global_overlays]` for `scope="global"`. This turned out to be load-bearing, not additive: every promoted project shares one physical Neo4j graph with no structural partitioning, and `find_impact()` as first written (this same session, before this fix) had **no project filter at all** — any project could already see every other project's dependents. Verified against real Neo4j: unrestricted, project-only, and project+overlay all return the expected distinct sets.
- **`kg_query`/`kg_search` fan-out — deferred, same reasoning as `at_commit`** (see Graph versioning above): `kg_query` executes arbitrary user-supplied Cypher text; safely injecting a `project_id IN [...]` filter into an arbitrary MATCH pattern isn't something we control, the same problem that blocked `at_commit`. `kg_search` doesn't exist yet (next build-order step) — whoever implements it should design its Claude-generated Cypher to include this filter from the start, rather than bolting it on after the fact the way `kg_query` would require.
- **Pre-existing gap found, not fixed here**: `recall.py`'s central KG query (`commands/recall.py`, Phase 3.3) has the identical issue — `MATCH (a:Artifact) WHERE a.path CONTAINS $q OR a.attrs CONTAINS $q ...` with no `project_id` filter at all. Out of scope for this component (it's already-shipped, tested Phase 3.3 code, not part of Federated overlays), but it's the same isolation gap and should be closed the same way — restrict to `[cfg.project.id, *cfg.federation.global_overlays]` — before relying on tenant isolation alone to mean "my project's data stays private from other teams in the same tenant."

---

## Build order

```
1. Design spike: RBAC token protocol (required before step 2)
2. RBAC token schema + admin CLI + MCP enforcement
3. cartographer seed --diff (incremental re-indexing)
4. cartographer promote --diff
5. CI templates (GitHub Actions, GitLab CI)
6. Graph versioning (PromotionRecord + cartographer log + at_commit filter)
7. kg_impact tool
8. Edge taxonomy document + lint step in seed + taxonomy_version pinning
9. cartographer taxonomy list command
10. kg_search tool (requires anthropic SDK dep)
11. Federated overlays (global_overlays config + query fan-out)
12. cartographer doctor enterprise checks
13. ADRs for RBAC model and kg_search implementation approach
```

---

## Open questions

| Question | Blocks |
|---|---|
| Token storage: central backend table vs. separate auth service | RBAC implementation (step 2) |
| Token validation latency budget: inline vs. cached | RBAC enforcement in MCP servers |
| `kg_search` Claude model: which model, what latency target | kg_search implementation |
| Overlay read authorization: does overlay access require a separate token or inherit from team token? | Federated overlays |
| Taxonomy enforcement: warning vs. error default in CI | Lint step in seed |

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | Team token scoped to project A cannot read project B | Issue token for project A; attempt `kg_query` against project B node; confirm `PERMISSION_DENIED` |
| 2 | `cartographer seed --diff` ingests only changed files | Modify 3 files; run seed --diff; confirm only 3 files processed in output |
| 3 | CI template runs seed + promote on merge to main without manual intervention | Merge a PR; observe CI run; confirm global index is updated within CI runtime |
| 4 | `kg_impact` returns cross-project dependents for a promoted symbol | Promote symbol A from project X; project Y imports A; run kg_impact on A; confirm project Y appears |
| 5 | Unknown edge type at seed time logs warning and is skipped | Add unknown edge type via enricher; run seed; confirm warning in output; confirm edge not written |
| 6 | `--strict` flag causes seed to fail on unknown edge type | Same as above with --strict; confirm exit code 1 |
| 7 | `kg_search` answers a structural question without the agent writing Cypher | Ask "what calls _build_prompt?"; confirm tool call succeeds and returns correct callers |
| 8 | `cartographer log` lists promotion history with commit SHAs | Promote twice from different commits; run cartographer log; confirm both entries with correct SHAs |
| 9 | All Phase 3 exit criteria still pass after Phase 4 changes | Re-run Phase 3 acceptance tests; confirm no regression |

---

*For phase exit criteria summary, see [ROADMAP.md](../ROADMAP.md). For Phase 3 foundation, see [phase-3-sync-lifecycle.md](phase-3-sync-lifecycle.md).*
