# ADR-0008: kg_search uses a direct Claude API call, not a recursive MCP call

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-05 |
| Deciders | Hendrick |

---

## Context

`kg_query` requires the calling agent to write raw Cypher against the knowledge graph's schema. This is a barrier for any agent session that isn't tuned to that schema, and query quality depends entirely on how well CLAUDE.md documents it. `kg_search` (Phase 4) translates a natural-language question into Cypher automatically.

`kg_search` is itself exposed as an MCP tool — a Claude Code session calls it mid-conversation, the same way it calls `kg_query`. The question this ADR resolves: how does the Cypher translation happen, given that the caller is already an active Claude Code agent loop?

---

## Decision

`kg_search`'s implementation (`cartographer/kg_search.py`) makes a direct `anthropic` SDK call (`anthropic.Anthropic(api_key=...).messages.create(...)`) using a key read from `cartographer.local.toml`'s `anthropic_api_key` field (or `CARTO_ANTHROPIC_API_KEY`/`ANTHROPIC_API_KEY` env vars, consistent with the CI-friendly override pattern already established for central backend credentials). It does not invoke the calling Claude Code session recursively, and it does not spawn a nested Claude Code subprocess.

Model: `claude-haiku-4-5-20251001` — NL-to-Cypher translation against a small, fixed schema is a well-defined, low-complexity task; a fast/cheap model is the right fit, not a reason to default to a larger one. Retry budget: 3 attempts, feeding the previous query and its execution error back into the next prompt on failure.

---

## Options considered

**Option A: Direct Claude API call (chosen).** `kg_search`'s own Python code calls the Anthropic API directly, synchronously, within the MCP tool handler.

**Option B: Recursive call into the calling Claude Code session.** Have the MCP tool somehow ask the *calling* agent to generate the Cypher and call back.

**Option C: Spawn a separate `claude` CLI subprocess** (the pattern this project already uses for `--enrich`'s LLM-based KG enrichment, via `kg_enricher.py`'s `claude` CLI invocation).

Option B is unworkable and was never seriously on the table: an MCP tool handler is a synchronous function call from the agent's perspective — there is no mechanism for a tool implementation to "call back" into the session that invoked it without that session's own loop explicitly doing so, and attempting to simulate this would mean the tool blocking indefinitely waiting for a response that can only come from completing the very call that's waiting on it. This is the reentrant-deadlock pattern this ADR exists to rule out by construction, not something that needed to be prototyped to reject.

Option C (subprocess) was considered since it's the project's existing pattern for `--enrich`. Rejected for `kg_search` specifically: `--enrich` runs during `cartographer seed`, a long-running batch command where a ~30-60s-per-file subprocess spawn is an accepted cost already documented to the user ("Expect ~30-60s per file"). `kg_search` is a synchronous, in-conversation tool call where a Claude Code session is waiting on the result turn-by-turn; a subprocess spawn's startup and model-loading overhead would make every single question noticeably slower than a direct API call needs to be, for no accuracy benefit — the subprocess path still just calls the same underlying model API itself, through an extra process boundary.

---

## Consequences

**Positive:**
- No deadlock risk: a direct API call has a straightforward request/response lifecycle, no dependency on the calling agent's own loop making further progress.
- Reuses the override/env-var pattern already shipped for central backend credentials (`CARTO_CENTRAL_VDB_PASSWORD` etc.) — `anthropic_api_key` follows the identical lookup order (`cartographer.local.toml` → `CARTO_ANTHROPIC_API_KEY` → fallback to the SDK-standard `ANTHROPIC_API_KEY`), so this isn't a new config pattern to learn.
- `anthropic` is a genuinely optional dependency (`cartographer[kg-search]`) — a project that never uses this tool pays no cost.

**Negative / risks:**
- A second API key to provision and rotate, separate from whatever key the calling Claude Code session itself uses (if any) — `kg_search` cannot assume it can reuse the calling session's own credentials, since an MCP tool has no access to them.
- Cost and latency are incurred per `kg_search` call, on top of whatever the calling Claude Code session's own model usage already costs. For a question `kg_query` could answer directly with a well-documented schema, `kg_search` is strictly more expensive — it exists for the cases where writing the Cypher by hand is the actual barrier, not as a default replacement for `kg_query`.
- Retry logic depends on `query_fn` raising on failure rather than degrading silently — `kg_neo4j.Neo4jDriver.query()`'s existing contract swallows exceptions and returns `[]` (relied on by `recall.py`/`gc.py`/`promote.py`), so a new `query_raising()` method was added specifically for this, rather than changing `query()`'s behavior for its existing callers.

---

## Open questions

**Model choice beyond the initial default**: `claude-haiku-4-5-20251001` is hardcoded as `kg_search.MODEL`, overridable via the `model` parameter on `generate_cypher`/`run_kg_search` but not yet exposed as a `cartographer.toml` setting. If Cypher quality from Haiku proves insufficient for more complex schema questions in practice, promoting this to a config field (`[retrieval]` or a new `[kg_search]` section) is the natural next step — deferred until there's real usage data showing it's needed, not speculated now.

**Global-scope project isolation enforcement**: `generate_cypher` currently enforces that the LLM's generated query *references* `$allowed_projects` as a substring check before execution — a real but shallow guard (it does not verify the reference is in a position that actually restricts the returned rows, only that the token appears in the query text at all). This mirrors the same class of limitation already flagged for `kg_query`'s and `kg_search`'s broader federated-overlay fan-out in `phase-4-enterprise.md`'s alignment notes. Strengthening this (e.g. parsing the generated Cypher's WHERE clause structurally rather than substring-matching) is future work, not required to ship the achievable version of this feature now.

---

## Links

- Phase doc: [phase-4-enterprise.md](../phases/phase-4-enterprise.md), component 5 ("`kg_search` — natural language to Cypher")
- Related: `kg_neo4j.Neo4jDriver.query_raising` (added alongside this), `kg_impact`'s federated-overlay project_id filtering (same isolation mechanism, same session)
- MCP server implementation notes referenced by the original phase doc's "Design constraint" line: `cli/src/cartographer/runtime/mcp_servers/kg_server.py`'s module docstring

---

*ADRs are append-only. To supersede this decision, create a new ADR and update the Status field here to "Superseded by ADR-XXXX".*
