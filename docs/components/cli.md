# Component Spec: CLI (`cartographer`)

The CLI is the per-project setup and state provisioning tool. It handles workspace scaffolding, index provisioning, standards pack management, documentation seeding, promotion, and diagnostics. It is a Python package installable via pip, including from a git URL.

The plugin owns reusable runtime capability (skills, hooks, MCP servers). The CLI owns everything that must happen before the plugin can run and everything that requires direct interaction with the index outside of a Claude Code session.

---

## 1. Responsibilities

| Responsibility | Commands |
|---|---|
| Detect and report existing workspace config | `detect` |
| Scaffold workspace and provision index | `init` |
| Apply standards packs | `stack add` |
| Seed documentation into the index | `seed` |
| Promote merged artifacts to global index | `promote` |
| Query the index for debugging | `recall` |
| Browse the local knowledge layer visually | `ui` |
| Validate config and backend health | `doctor` |

---

## 2. Installation

Cartographer is not published to PyPI. Install directly from the repository:

```
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli"

# with the fastembed embedding driver
pip install "git+https://github.com/acn-hendrickacosta/cartographer.git#subdirectory=cli[embed]"
```

For local development (editable install):

```
git clone https://github.com/acn-hendrickacosta/cartographer.git
cd cartographer/cli
pip install -e ".[embed]"
```

Requires Python 3.11 or later. The local VDB (LanceDB) and KG (Kuzu) drivers are installed as dependencies. The `[embed]` extra adds the fastembed driver.

---

## 3. Config contract

Every command except `detect` and `init` requires a valid `cartographer.toml` in the project tree. Config is loaded using the precedence chain described in [CONFIGURATION.md](../CONFIGURATION.md):

```
CARTO_* environment variables > .cartographer.local.toml > cartographer.toml > defaults
```

If `cartographer.toml` is not found and the command requires it, the CLI exits with code `1` and the message:

```
cartographer: no cartographer.toml found. Run cartographer init first.
```

---

## 4. Command specifications

### 4.1 `cartographer detect`

**Purpose:** Dry run. Report what exists in the workspace and what `init` would do. Never writes anything.

**Usage:**
```
cartographer detect [--root <path>]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `--root` | current working directory | Project root to scan |

**Process:**
1. Scan workspace root for: `.claude/`, `CLAUDE.md`, `.mcp.json`, `.claude/settings.json`, `cartographer.toml`.
2. For each found file: report its location and what `init` would merge or leave unchanged.
3. For each missing file: report what `init` would create.
4. Report the current stack packs found in `.claude/standards/`, if any.

**Output:** Human-readable report to stdout. Structured JSON available with `--json`.

**Exit codes:** `0` always (detect never fails).

**Failure modes:** None. If the workspace root does not exist, reports it and exits `0`.

---

### 4.2 `cartographer init`

**Purpose:** Scaffold the workspace, provision the local index, and register the project. Idempotent.

**Usage:**
```
cartographer init [--root <path>] [--stack <name>]... [--seed-docs <path>] [--yes]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `--root` | current working directory | Project root to initialize |
| `--stack` | none | Stack pack name(s) to apply (repeatable). E.g. `--stack python --stack react` |
| `--seed-docs` | none | Path to a documentation directory or file to seed into the index immediately |
| `--yes` | false | Skip confirmation prompts and apply the merge plan automatically |

**Process:**
1. Assign or load `project_id` (generate UUID on first run; reuse from `cartographer.toml` on re-run).
2. Run detect scan.
3. Compute merge plan:
   - `CLAUDE.md` exists: plan additive merge of Cartographer project-knowledge section.
   - `.claude/settings.json` exists: plan additive merge of hook entries; deduplicate.
   - `.mcp.json` exists: plan additive merge of VDB and KG MCP server entries; deduplicate.
   - Missing files: plan fresh create.
4. Print merge plan. Prompt for confirmation unless `--yes`.
5. Execute plan: write or merge each file.
6. Write cross-stack standards baseline into `.claude/standards/cross-stack/`.
7. For each `--stack` flag: execute `stack add` logic.
8. Write `cartographer.toml` (shared config) and `.cartographer.local.toml` stub (gitignored).
9. Add `.cartographer.local.toml` to `.gitignore` if not already present.
10. Add `.cartographer/` to `.gitignore` if not already present.
11. Provision local VDB collection: call `vdb_ensure_collection(project_id, scope=local)`.
12. Provision local KG namespace: call `kg_ensure_namespace(project_id, scope=local)`.
13. Upsert project record into `~/.cartographer/registry.db`.
14. If `--seed-docs` given: run seed pipeline against the specified path.
15. Print summary of every file written, merged, or left unchanged.

**Output:** Structured summary to stdout. One line per file action (created / merged / unchanged).

**Exit codes:**
| Code | Condition |
|---|---|
| `0` | Success |
| `1` | Config validation failed |
| `2` | Backend provisioning failed (VDB or KG driver error) |
| `3` | User declined merge plan at confirmation prompt |

**Failure modes:**

| Failure | Behavior |
|---|---|
| VDB provisioning fails | Roll back all written files (restore from backups taken in step 5), exit `2`, print driver error |
| KG provisioning fails | Same rollback, exit `2` |
| Existing file cannot be parsed for merge | Skip the merge for that file, leave it unchanged, print a warning, continue |
| `.gitignore` is missing | Create it with the two entries; do not fail |

**Idempotency:** Running `init` a second time on an already-initialized workspace is safe. Files already containing Cartographer entries are not duplicated. The VDB and KG provisioning calls are idempotent. The registry upsert is idempotent.

---

### 4.3 `cartographer stack add <name>`

**Purpose:** Apply a standards pack into the workspace.

**Usage:**
```
cartographer stack add <name>
```

**Inputs:**

| Argument | Description |
|---|---|
| `name` | Pack name. Currently supported: `python`, `react`. |

**Process:**
1. Load config.
2. Resolve pack content:
   - If `stacks.registry_url` is configured: attempt to fetch the latest published version from the Standards Registry. On failure (network error, 4xx, 5xx): fall back to bundled version and log a warning with the registry URL and error.
   - If `stacks.registry_url` is not configured: use bundled version.
3. Copy pack markdown into `.claude/standards/<name>/`.
4. If the pack includes optional hook additions or skills: merge them additively into the workspace.
5. Update `stacks.active` in `cartographer.toml` to include `<name>` if not already present.
6. Print what was written.

**Exit codes:** `0` success, `1` pack name not recognized, `2` file write failed.

**Failure modes:**

| Failure | Behavior |
|---|---|
| Registry fetch fails | Fall back to bundled pack, log warning, continue |
| Pack name not recognized | Exit `1` with message listing supported packs |
| Destination files already exist | Overwrite with confirmation prompt (or `--yes`) |

---

### 4.4 `cartographer seed <path>`

**Purpose:** Ingest a documentation source into the local index immediately, outside the normal hook-triggered ingestion cycle. With `--enrich`, uses the local `claude` CLI to extract richer semantic KG relationships beyond what static analysis provides.

**Usage:**
```
cartographer seed <path> [--recursive] [--enrich]
```

**Inputs:**

| Argument/Flag | Default | Description |
|---|---|---|
| `path` | required | File, directory, or glob pattern to ingest |
| `--recursive` | true for directories | Walk subdirectories when `path` is a directory |
| `--enrich` | false | Call the local `claude` CLI per file to extract semantic KG relationships. Requires `claude` on PATH. Adds `concept` nodes and typed edges (validates, renders, persists, etc.) that regex extraction cannot produce. Expect 30-60 seconds per file. |

**Supported formats:** `.md`, `.rst`, `.txt`, `.adoc`, `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, and other plain-text code and config extensions.

**Process:**
1. Load config.
2. Resolve `path` to a list of files, skipping hidden directories and common artifact directories (`.git`, `node_modules`, `.angular`, `.next`, etc.).
3. Filter to supported formats. Skip and warn on unsupported extensions.
4. If `--enrich` is set: verify `claude` is on PATH. Exit with a clear error if not found.
5. For each file, show a progress bar (file N of total):
   a. Read file content as plain text.
   b. Chunk text at symbol or heading boundaries (fallback: fixed-size sliding window).
   c. Embed chunks using the local fastembed model.
   d. Extract KG nodes and edges using regex-based static analysis (imports, symbol definitions, spec references).
   e. If `--enrich`: call `claude -p` with the file content and a structured extraction prompt. Parse the JSON response. Merge Claude-produced `implements`, `depends_on`, and `relationships` into the KG graph as additional nodes and edges. Concept targets that do not map to a real file are written as `concept` stub nodes so edges can be created immediately.
   f. `vdb_upsert` chunks to local scope.
   g. `kg_upsert_nodes` and `kg_upsert_edges` to local scope.
6. Print summary: files processed, chunks written, nodes and edges upserted, files skipped, errors.

**Exit codes:** `0` success (even if some files were skipped), `1` config not found, `2` no supported files found at path.

**Failure modes:**

| Failure | Behavior |
|---|---|
| Binary file, Claude not available | Skip file, warn, continue. Print count of skipped files in summary. |
| File unreadable (permissions) | Skip file, warn, continue |
| Embedder unavailable | Exit `2` after first failure; do not leave partial results |
| VDB or KG write fails | Exit `2` after first failure; do not leave partial results |

---

### 4.5 `cartographer promote`

**Purpose:** Promote merged artifacts from local scope to global scope in the central backend. No-op in local-only topology.

**Usage:**
```
cartographer promote [--full] [--dry-run]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `--full` | false | Re-promote all artifacts, not just those changed since last promotion |
| `--dry-run` | false | Report what would be promoted without writing anything |

**Process:**
1. Load config. If `topology.mode = "local"`: print message and exit `0`.
2. Validate central backend reachability (VDB endpoint + API key, KG endpoint + API key).
3. Determine promotion scope:
   - Default: artifacts changed since `last_promoted_at` in registry (via `git log --since`).
   - `--full`: all artifacts in the local index.
4. If `--dry-run`: print artifact list and exit `0`.
5. For each artifact in scope:
   - Re-ingest against global scope (same pipeline as seed/hook, but `scope=global`).
   - `vdb_upsert` to global scope.
   - `kg_upsert_nodes` and `kg_upsert_edges` to global scope.
6. Update `last_promoted_at` in the registry.
7. Print count of artifacts promoted.

**Exit codes:** `0` success or local-only topology, `1` central backend unreachable, `2` promotion pipeline error.

**Failure modes:**

| Failure | Behavior |
|---|---|
| Central backend unreachable | Exit `1`; no partial writes |
| API key rejected | Exit `1` with auth error message |
| Individual artifact ingestion fails | Log the artifact identity and error, continue with remaining artifacts, exit `2` at end |

---

### 4.6 `cartographer recall <query>`

**Purpose:** Query the index and print results. Debugging aid. The primary recall path is the `UserPromptSubmit` hook.

**Usage:**
```
cartographer recall "<query>" [--scope <scope>] [--top-k <n>] [--project <project_id>]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `query` | required | Natural language query string |
| `--scope` | `local` | `local`, `global`, or `both` |
| `--top-k` | `8` | Number of VDB results to return |
| `--project` | current project | Project ID to query (for cross-project recall, must share tenant) |

**Process:**
1. Load config.
2. If `--project` differs from current project: load target project from registry, verify tenant match.
3. `vdb_query` against specified scope(s).
4. `kg_neighbors` for each top VDB result (depth 1).
5. Merge and print results with scores, paths, and origin tags.

**Exit codes:** `0` success, `1` tenant isolation violation, `2` backend error.

---

### 4.7 `cartographer ui`

**Purpose:** Launch a lightweight local web server that lets a developer browse their local VDB and KG visually. Useful for verifying that the knowledge layer is populated correctly and for exploring what Cartographer knows about a project.

**Usage:**
```
cartographer ui [--port <port>] [--no-open]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `--port` | `7341` | Port to bind the local server to |
| `--no-open` | false | Start the server but do not open a browser tab automatically |

**Process:**
1. Load config.
2. Verify local VDB collection and KG namespace exist. If not: print message directing the developer to run `cartographer init`, exit `1`.
3. Start a FastAPI server on `localhost:<port>`.
4. Open the default browser to `http://localhost:<port>` unless `--no-open` is set.
5. Serve the UI until the developer stops the process (Ctrl+C).

**UI views:**

| View | What it shows |
|---|---|
| Search | A query input; runs `vdb_query` against the local index; displays scored results with path, artifact type, origin, and the first 3 lines of chunk text |
| Graph | A force-directed graph of KG nodes and edges; click a node to see its attrs and neighbors; filter by node type and edge type |
| Registry | All projects registered on this machine: project name, topology, active stacks, last indexed at |
| Stats | Chunk count, node count, edge count per artifact type; last indexed timestamp |

**Tech stack:**
- Backend: FastAPI (lightweight, already a Python dependency)
- Frontend: single-page HTML/JS served from `cli/src/cartographer/ui/` as static files; no build step required
- Graph visualization: D3.js (loaded from CDN; requires a browser with internet access for the graph view -- gracefully degrades to a node list if CDN is unreachable)
- No framework (no React, no Vue): plain HTML, CSS, and vanilla JS to keep the bundle zero-dependency

**Exit codes:** `0` on clean Ctrl+C shutdown, `1` if index not provisioned or port already in use.

**Failure modes:**

| Failure | Behavior |
|---|---|
| Port already in use | Print message suggesting `--port <other>`, exit `1` |
| VDB or KG unavailable after startup | Display error state in the UI; do not crash the server |
| Browser fails to open | Print the URL to stdout; server continues running |

---

### 4.8 `cartographer doctor`

**Purpose:** Validate config, backend reachability, and plugin wiring. Returns a pass/fail report.

**Usage:**
```
cartographer doctor [--fix]
```

**Inputs:**

| Flag | Default | Description |
|---|---|---|
| `--fix` | false | Attempt to auto-fix simple issues (re-add missing gitignore entries, re-provision missing collections) |

**Checks performed:**

| Check | Failure action |
|---|---|
| `cartographer.toml` is present and schema-valid | Fail |
| `cartographer.toml` contains no secret-pattern strings | Fail with offending field name |
| `.cartographer.local.toml` is listed in `.gitignore` | Warn (fix with `--fix`) |
| `.cartographer/` is listed in `.gitignore` | Warn (fix with `--fix`) |
| `.claude/settings.json` contains expected hook entries | Warn |
| `.mcp.json` contains expected MCP server entries | Warn |
| Local VDB collection exists and is reachable | Fail |
| Local KG namespace exists and is reachable | Fail |
| Embedding dimensions in config match existing collection | Fail |
| `project.id` in config matches registry entry for this root | Warn |
| Central VDB endpoint reachable and API key accepted | Fail (if topology = central) |
| Central KG endpoint reachable and API key accepted | Fail (if topology = central) |

**Exit codes:** `0` all checks pass, `1` one or more checks failed, `2` one or more warnings (no failures).

---

## 5. Output conventions

- All output goes to stdout. Errors and warnings go to stderr.
- `--json` flag available on all commands for machine-readable output.
- Logs (not user output) go to `~/.cartographer/cli.log`. Log level configurable via `CARTO_LOG_LEVEL` (`debug`, `info`, `warn`, `error`).
- Exit codes are documented per command. `0` always means success.

---

## 6. Global flags

| Flag | Description |
|---|---|
| `--root <path>` | Override project root detection |
| `--config <path>` | Use a specific `cartographer.toml` instead of the detected one |
| `--json` | Machine-readable JSON output |
| `--quiet` | Suppress all output except errors |
| `--version` | Print CLI version and exit |

---

*For configuration reference, see [CONFIGURATION.md](../CONFIGURATION.md). For the VDB and KG tool contracts the CLI calls, see [contracts/vdb-tools.md](../contracts/vdb-tools.md) and [contracts/kg-tools.md](../contracts/kg-tools.md).*
