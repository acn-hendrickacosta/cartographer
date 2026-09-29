# Cartographer CLI

Persistent knowledge layer for Claude Code. Cartographer indexes your codebase into a local vector database and knowledge graph, keeps that index current automatically, and surfaces relevant context in every Claude Code session — without you asking for it and without relying on the model to remember anything.

- **Semantic search** over code, docs, and specs (`vdb_search`)
- **A real knowledge graph** of `calls`/`imports`/`extends`/`defines` edges, extracted via language parsers, not guesswork (`kg_query`, `kg_neighbors`)
- **Always up to date**: a background watcher re-indexes changed files automatically, independent of Claude Code hooks
- **A local browser UI** (`cartographer ui`) to search, explore the graph, and see index stats without leaving your terminal
- **Optional shared/central index** so a team sees each other's promoted knowledge, not just their own machine's

---

## How it works, in one paragraph

`cartographer init` provisions a local index (LanceDB for vectors, Kuzu for the graph) and registers your project. `cartographer seed` does the first full pass. After that, a background watcher (`cartographer serve --watch`, on by default) notices changed files and re-indexes them automatically — no manual re-seeding, no relying on Claude Code hooks firing correctly. Claude Code talks to the index via two local MCP servers (`vdb_search`, `kg_query`, etc.). `cartographer ui` gives you a visual way to poke at the same index yourself. Everything above is **local-only** by default; a `central` topology (below) adds a shared index so a team's promoted knowledge is visible across machines.

---

## Install

```bash
pipx install --editable ".[embeddings,mcp]"
```

Or for a shared team install, each developer runs:

```bash
pipx install "git+https://<host>/<org>/cartographer.git#subdirectory=cli[embeddings,mcp]"
```

**pipx vs. plain `pip install`:** pipx-managed environments do not ship a `pip` binary inside them. If you installed via pipx and later need to add an optional extra (e.g. TypeScript parsing), use `pipx inject`, not `pip install` — see [Troubleshooting](#troubleshooting).

---

## Quickstart

```bash
# 1. Initialize a project (run once per project)
cd /your/project
cartographer init

# 2. Index the codebase (first full pass)
cartographer seed .

# 3. Start the MCP servers + background watcher (run once per machine, keep it running)
cartographer serve

# 4. Open Claude Code in this project — it uses the index automatically
```

After `cartographer init`, two MCP server entries are written to `.mcp.json`. Add them to Claude Code at User scope via **Settings → MCP Servers → Add**, using the URLs printed by `cartographer serve` (defaults: `http://localhost:4010/mcp` for VDB, `http://localhost:4011/mcp` for KG).

Want to look around before wiring anything into Claude Code? Run `cartographer ui` — it opens a browser you can search and explore the graph in immediately after step 2.

---

## Keeping the index current

This is the part that matters most and is easy to get wrong assumptions about, so it's worth its own section.

**`cartographer init` wires four Claude Code hooks** (`PostToolUse`, `Stop`, `SessionStart`, `UserPromptSubmit`) into the project's `.claude/settings.json`, so edits made *during a Claude Code session* get queued and flushed automatically, and relevant context gets injected at session start and on every prompt.

**But hooks alone are not enough, and sometimes don't run at all:**
- Hooks only fire on Claude Code's own tool calls. A `git pull`, a branch switch, a teammate's commit, or an edit from any other tool never triggers a hook — the index would silently drift stale.
- Some enterprise Claude Code deployments set `"allowManagedHooksOnly": true` in managed settings. Under that policy, hooks defined in a *project's own* `.claude/settings.json` — including Cartographer's — are silently ignored. Run `cartographer doctor` to check; if hooks aren't firing, this is the first thing to look at.

**The fix for both problems is the same: `cartographer serve --watch` (on by default).** It runs a real filesystem watcher (via `watchdog`, OS-level events, not polling) inside the same process you already have to run for MCP to work. It watches every project you've registered via `cartographer init`, debounces bursts of changes (3s idle), and re-ingests changed files using the exact same pipeline `cartographer seed` uses. It doesn't touch Claude Code's hook system at all, so it works regardless of `allowManagedHooksOnly`, and it catches changes hooks structurally never could (a `git pull`, another tool's edit).

In short: **run `cartographer serve` and leave it running.** The hooks are a nice-to-have for context injection; the watcher is what actually keeps the index from going stale.

---

## Commands

### `cartographer init`

Scaffolds the project: writes `CLAUDE.md` (Cartographer section), wires the four Claude Code hooks into `.claude/settings.json`, writes `.mcp.json`, provisions the local index (LanceDB + Kuzu), applies the cross-stack standards baseline, and registers the project in a global registry (`~/.cartographer/registry.json`).

```bash
cartographer init                        # in the project root
cartographer init --stacks python,react  # with language-specific standards packs
cartographer init --topology central     # opt into a shared team index (see Central topology, below)
cartographer init --name my-project      # override the registered project name (default: directory name)
```

Idempotent and safe to re-run: existing `CLAUDE.md`/`.claude/settings.json` content is merged, not clobbered (your own hooks and permissions on the same event survive), and re-running with no `--topology` flag preserves whatever topology is already configured rather than silently resetting it to `local`.

---

### `cartographer seed <source>`

Indexes a file, directory, or single-file target into the local VDB and KG. This is the first full pass; after that, `cartographer serve --watch` keeps things current automatically — you shouldn't need to re-run `seed` by hand except after installing a new language parser (see below) or recovering from a rebase.

```bash
cartographer seed .                       # index the whole project
cartographer seed src/                    # index a subdirectory
cartographer seed docs/spec.md            # index a single file
cartographer seed . --no-recursive        # only the top level of a directory
cartographer seed . --enrich              # also extract LLM-derived semantic relationships (slower)
```

**Without `--enrich`** (default): uses the language parser layer to extract structural edges — `calls`, `imports`, `extends`, `defines`. Fast, fully offline, no extra dependencies beyond what you installed for your language.

**With `--enrich`**: additionally shells out to the local `claude` CLI, once per file, to extract semantic relationships (`implements_spec`, `depends_on`, freeform `relates_to`-style edges, and per-file concept nodes) from doc and spec files. Requires `claude` on PATH. Expect ~30–60s *per file* — for a few hundred files this can take a long time and has real Claude usage cost, so consider running it on a subset first. Since seeding is upsert-based, running `--enrich` later doesn't require a fresh `seed` — it adds the semantic layer on top of whatever structural index already exists.

Files matching common ignore patterns (`.git`, `node_modules`, `__pycache__`, `.venv`, build/cache directories for most JS/TS frameworks) are skipped automatically, recursively.

**If you need a truly clean re-seed** (e.g. after fixing a parser bug, or after a force-push/rebase that deleted files):

```bash
rm -rf .cartographer/local/
cartographer seed .
```

---

### `cartographer stack add <name>`

Applies a bundled standards pack — plain markdown guidance copied into `.claude/standards/<name>/` — and records it as an "active stack" in `cartographer.toml`.

```bash
cartographer stack add python
cartographer stack add react
```

Known packs today: `cross-stack` (applied automatically by `init`), `python`, `react`.

For stacks whose language needs a real AST parser to get full graph fidelity (currently: `react`, which needs the TypeScript grammar), `stack add` checks whether that parser is actually installed and — if not — prints the exact command to fix it, correctly adapted to how you installed Cartographer:

```
note: 'react' parses .ts/.tsx files with a regex fallback until the real parser is
installed (no calls/extends edges in the KG). Install with:
  pipx inject cartographer "tree-sitter>=0.23" "tree-sitter-typescript>=0.23"
```

(or `pip install 'cartographer[parsers-ts]'` if you're not on pipx). `cartographer doctor` runs this same check on every run, not just at `stack add` time, so it'll catch a parser that's missing after a fresh clone too.

---

### `cartographer serve`

Starts both MCP servers as persistent HTTP processes on localhost, plus the background filesystem watcher (see [Keeping the index current](#keeping-the-index-current)). This is the one long-running process you keep open.

```bash
cartographer serve                             # default: VDB on :4010, KG on :4011, watcher on
cartographer serve --vdb-port 4020 --kg-port 4021
cartographer serve --no-watch                  # MCP only, no background re-indexing
```

The MCP servers handle every registered project from a single instance — workspace is routed per-request via the `?workspace=` URL parameter that `cartographer init` writes into `.mcp.json`. The watcher similarly covers **every project you've ever run `cartographer init` in**, not just the one you happened to start `serve` from — it re-checks the registry every 10 seconds, so newly `init`'d projects are picked up without restarting `serve`.

**Enterprise note:** `cartographer serve` uses HTTP rather than stdio because enterprise Claude Code policies commonly block stdio MCP servers; HTTP localhost servers are explicitly allowed. The watcher exists for the analogous reason on the hooks side — see above.

---

### `cartographer ui`

Launches a local web UI (FastAPI + a single static page, no build step for you to run) for browsing whatever `cartographer serve`/`seed` has indexed.

```bash
cartographer ui                    # opens a browser at http://127.0.0.1:7341
cartographer ui --port 8080        # use a different port
cartographer ui --no-browser       # print the URL instead of auto-opening a tab
```

Requires the `ui` extra (`fastapi`, `uvicorn`) — install with `pipx inject cartographer fastapi "uvicorn[standard]"` or `pip install 'cartographer[ui]'`.

What's in it:

- **Explore — Search**: live semantic search as you type, filterable by artifact type (Doc/Code/Spec), with a relevance bar per result and a truncate/expand toggle for long snippets. Click any result to jump straight into its graph neighborhood.
- **Explore — Browse**: a collapsible file tree (module/doc/spec nodes from the knowledge graph) as a second way into the graph, for when you don't already know what to search for. Has its own filter box that auto-expands matching branches.
- **Graph**: pan/zoom, drag nodes, click a node to see its detail panel and an "Explore from here →" button that re-centers the graph on it (with a Back button, so this is real drill-down navigation, not a one-shot query). Hover any edge to see its exact relationship type and meaning. A legend explains every node color and relationship type.
- **Registry**: every project registered on this machine, with the currently-open one highlighted.
- **Stats**: chunk/node counts by type for the current project's local index, as proportional bars.

This UI only ever shows the **local** index of whatever project you launched it against — it does not query a central/shared index, by design (that's a separate concern from browsing your own machine's knowledge).

---

### `cartographer doctor`

Validates the installation end to end. Run this first whenever something seems off.

Checks performed:
- `cartographer.toml` exists and parses
- Local VDB and KG are readable
- If `topology = central`: promotion token is set, and both the central VDB (pgvector) and central KG (Neo4j) are reachable — with a specific, actionable message for each failure mode (missing driver package, missing credentials, connection refused)
- Cartographer's MCP entries are present in `.mcp.json`
- For every active stack that expects a real AST parser (currently: `react`): whether that parser is actually installed, with the exact install command if not

```bash
cartographer doctor
```

---

### `cartographer detect`

Read-only report of what `cartographer init` would create or merge in the current directory — safe to run before committing to `init`, especially on a project with existing Claude Code configuration you don't want to overwrite.

```bash
cartographer detect
```

---

### `cartographer recall <query>`

A debugging/inspection command — queries the local KG and VDB directly and prints matches, enforcing the same tenant-isolation rule Claude Code's recall skill uses (never returns results across a tenant mismatch, even locally). This is not the primary way Claude gets context during a session — that's the `retrieve`/`preload` hooks and the MCP tools — this command exists for when you want to check "does the index actually contain X" from the terminal.

```bash
cartographer recall "embedding retry logic"
cartographer recall "auth middleware" --k 15
```

---

### `cartographer promote`

In `local` topology: a no-op (nothing to promote to). In `central` topology: promotes your local index into the shared central index so teammates see your work.

```bash
cartographer promote                # incremental: only what changed since last promote
cartographer promote --full         # re-promote everything, not just changed artifacts
cartographer promote --dry-run      # report what would be promoted, write nothing
```

---

## Central topology (advanced)

By default every project is `local`-only — your own machine, your own index. Opting into `central` gives you a shared index (pgvector for vectors, Neo4j for the graph) so a team sees each other's promoted knowledge, not just their own local work.

```bash
cartographer init --topology central
```

This writes `.cartographer.local.toml` (gitignored — it holds per-developer secrets) with a `[central_vdb]` and `[central_kg]` section to fill in:

```toml
[central_vdb]
host = "localhost"
port = 5432
user = "cartographer"
password = ""        # fill this in
database = "cartographer"

[central_kg]
uri = "bolt://localhost:7687"
user = "neo4j"
password = ""        # fill this in
```

A promotion token is generated automatically the first time you initialize with `--topology central`. Run `cartographer doctor` after filling in credentials to confirm both backends are reachable before promoting.

Local always wins for reads: if you have local, uncommitted changes to a file, your session sees your local version, not the last-promoted one, even after your teammate has promoted a different version. Promotion pushes local knowledge outward; it never overwrites what you're actively working on.

---

## Language support

| Language | Parser | What you get |
|---|---|---|
| Python | stdlib `ast` — built in, no install needed | Full structural edges: `calls`, `imports`, `extends`, `defines` |
| TypeScript / TSX | `tree-sitter-typescript` — install the `parsers-ts` extra | Full structural edges, including member-expression calls (`this.foo()`, `obj.bar()`) and multi-parent interface `extends` |
| Everything else | regex fallback — always active, no install needed | `defines` (top-level functions/classes only) and relative-import `imports` edges only — **no `calls` or `extends` edges**, regex can't do that reliably |

`parsers-go` and `parsers-rust` extras exist in `pyproject.toml` but have no parser implementation behind them yet — installing them currently does nothing; Go and Rust files still use the regex fallback. Don't rely on the extras table below implying otherwise for those two.

Install the TypeScript grammar with:

```bash
pipx inject cartographer "tree-sitter>=0.23" "tree-sitter-typescript>=0.23"
# or, if you're on plain pip:
pip install 'cartographer[parsers-ts]'
```

After installing a parser for the first time, do a clean re-seed to upgrade already-indexed files from the regex fallback to real structural edges:

```bash
rm -rf .cartographer/local/
cartographer seed .
```

---

## MCP tools

Once `cartographer serve` is running and the servers are registered in Claude Code, these tools are available in every session:

### VDB tools (port 4010 by default)

| Tool | What it does |
|---|---|
| `vdb_search(query, workspace)` | Semantic search — find files, specs, and docs relevant to a concept or task |
| `vdb_stats(workspace)` | Chunk counts per artifact type — confirms the index is populated |

### KG tools (port 4011 by default)

| Tool | What it does |
|---|---|
| `kg_query(cypher, workspace)` | Execute a Cypher query against the knowledge graph |
| `kg_neighbors(node_id, workspace, depth)` | Get neighboring nodes at a given traversal depth |
| `kg_stats(workspace)` | Node and edge counts |

**Always pass `workspace`** — the server is shared across every registered project and cannot infer which one you mean.

### Knowledge graph edge types

| Edge type | Source | Meaning |
|---|---|---|
| `defines` | AST / regex | File defines a symbol |
| `calls` | AST (regex: none) | Function/method A calls function/method B |
| `imports` | AST / regex | File A imports file B |
| `extends` | AST (regex: none) | Class/interface A extends/inherits from B |
| `implements_spec` | Regex (always) / LLM (`--enrich`) | File references a spec, or an LLM-identified semantic implementation relationship |
| `depends_on` | LLM (`--enrich`) | Semantic dependency identified by the enricher |

Example Cypher queries:
```cypher
-- What calls _build_prompt?
MATCH (a:Artifact)-[r:RelatesTo {type: 'calls'}]->(b:Artifact)
WHERE b.attrs CONTAINS '_build_prompt' RETURN a.path LIMIT 20

-- What would break if I change BaseValidator?
MATCH (a:Artifact)-[r:RelatesTo {type: 'extends'}]->(b:Artifact)
WHERE b.attrs CONTAINS 'BaseValidator' RETURN a.path LIMIT 10
```

---

## Optional extras

| Extra | What it adds | When you need it |
|---|---|---|
| `embeddings` (alias `embed`) | `fastembed` for semantic VDB search | Required for `vdb_search`, `recall`, and `cartographer ui`'s Search tab |
| `mcp` | MCP SDK for the HTTP servers | Required for `cartographer serve` |
| `ui` | `fastapi` + `uvicorn` | Required for `cartographer ui` |
| `parsers-ts` | `tree-sitter` + `tree-sitter-typescript` | Real structural parsing for `.ts`/`.tsx` (see [Language support](#language-support)) |
| `parsers-go` | `tree-sitter` + `tree-sitter-go` | **Not yet functional** — no Go parser implementation exists yet; installing this does nothing today |
| `parsers-rust` | `tree-sitter` + `tree-sitter-rust` | **Not yet functional** — same as above, for Rust |
| `parsers-all` | All of the above tree-sitter grammars | Only actually enables TypeScript today, for the reason above |
| `central` | `psycopg2-binary` + `neo4j` | Already included in core dependencies — this extra is redundant but harmless to specify |
| `dev` | `pytest`, `httpx` | Running the test suite |

Python and the regex fallback need nothing extra. `psycopg2-binary` and `neo4j` ship in core dependencies, so central topology works with zero extra install step.

---

## Troubleshooting

**`pip install 'cartographer[...]'` fails with `No module named pip`.** You're on a pipx-managed install — those venvs don't ship `pip` at all. Use `pipx inject` instead:

```bash
pipx inject cartographer <package> [<package> ...]
```

`pipx install 'cartographer[extra]'` on an *already-installed* package also won't work — pipx refuses to modify an existing install (`'cartographer' already seems to be installed`) unless you pass `--force`. `pipx inject` is the correct tool for "add a package to an app I've already installed."

**Hooks don't seem to fire; files don't get re-ingested during a session.** Check whether your organization's Claude Code deployment sets `"allowManagedHooksOnly": true` in managed settings — under that policy, a project's own `.claude/settings.json` hooks (including Cartographer's) are silently ignored. This is exactly what `cartographer serve --watch` is for: it doesn't depend on hooks at all. Make sure `cartographer serve` is actually running.

**`cartographer doctor` shows a central VDB/KG failure.** The message tells you exactly what's missing (driver not installed vs. credentials not set vs. connection refused) — fix that specific thing and re-run `doctor` rather than guessing.

**A file was renamed or deleted and the old path still shows up in search/graph results.** Cartographer's ingestion is currently upsert-only — nothing automatically removes entries for files that no longer exist. Do a clean re-seed: `rm -rf .cartographer/local/ && cartographer seed .`.

---

## Updating

After pulling new code, for an editable pipx install:

```bash
uv pip install -e /path/to/cartographer/cli \
  --python "$(pipx environment --value PIPX_LOCAL_VENVS)/cartographer/bin/python3" \
  --no-deps -q
```

Then restart `cartographer serve`. If the update added a new dependency (check `pyproject.toml`'s `dependencies` list), you'll also need `pipx inject cartographer <the new package>` — an editable install picks up source changes immediately, but never installs new dependencies on its own.
