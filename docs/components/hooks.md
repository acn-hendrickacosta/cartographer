# Component Spec: Hooks

Hooks are the always-on, deterministic layer of Cartographer. They ensure the knowledge layer stays current and that relevant knowledge is injected into every Claude Code session and every prompt turn, without relying on the model to remember to do it.

This document defines the three hooks, their contracts, their portability rules, and their failure handling.

---

## 1. The fundamental rule

Model-invoked work goes in skills. Guaranteed always-on work goes in hooks.

A skill can be forgotten. A hook fires deterministically on its event. Any capability that must happen on every turn, every session start, or every file edit must be a hook. Any capability that is deliberate, one-time, or requires judgment may be a skill.

---

## 2. Hook inventory

| Hook name | Event | Purpose |
|---|---|---|
| `ingest` | `PostToolUse` (enqueue) + `Stop` or git commit (flush) | Capture code, spec, and doc changes into local VDB and KG |
| `preload` | `SessionStart` | Inject scoped context for the current working set into session context |
| `retrieve` | `UserPromptSubmit` | Inject per-turn relevant knowledge into each prompt |

All three hooks are defined in `hooks.json` inside the plugin package and are merged into `.claude/settings.json` at `cartographer init`.

---

## 3. Portability rules

Hook scripts must be portable across machines and project checkouts. All hooks follow these rules:

| Rule | Detail |
|---|---|
| Reference scripts via `${CLAUDE_PLUGIN_ROOT}` | Never use absolute paths in `hooks.json`. `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin install directory at runtime. |
| Read project root via `$CLAUDE_PROJECT_DIR` | The project root is injected by Claude Code. Do not infer it from `__file__` or `pwd`. |
| Pass state between hooks via `$CLAUDE_ENV_FILE` | The `SessionStart` hook writes project metadata to `$CLAUDE_ENV_FILE`. Subsequent hooks in the same session read from this file. |
| Write scratch files to `$CLAUDE_PROJECT_DIR/.cartographer/` | The dirty queue and session state files live here, not in `/tmp`. |
| Never require interactive input | Hooks run non-interactively. Any operation that would prompt the user must be skipped or deferred. |
| Must complete within 10 seconds | Hooks that exceed the timeout are killed. Embed and graph operations are deferred to the flush path for this reason. |

---

## 4. Hook definitions (`hooks.json`)

```json
{
  "hooks": [
    {
      "name": "cartographer-ingest-enqueue",
      "event": "PostToolUse",
      "tools": ["Write", "Edit"],
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest_enqueue.py"
    },
    {
      "name": "cartographer-ingest-flush",
      "event": "Stop",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/ingest_flush.py"
    },
    {
      "name": "cartographer-preload",
      "event": "SessionStart",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/preload.py"
    },
    {
      "name": "cartographer-retrieve",
      "event": "UserPromptSubmit",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/scripts/retrieve.py"
    }
  ]
}
```

---

## 5. Hook specifications

### 5.1 Ingest enqueue (`PostToolUse`)

**Event:** `PostToolUse`, filtered to `Write` and `Edit` tools only.

**Purpose:** Mark files as dirty for the next flush. Must complete instantly. Must not embed or write to the VDB or KG.

**Contract:**
- Input: the `PostToolUse` payload, which includes the tool name and the file path written or edited.
- Operation: append the file path and its inferred `artifact_type` to the dirty queue file at `$CLAUDE_PROJECT_DIR/.cartographer/dirty_queue.jsonl`. One JSON line per entry.
- Output: nothing to stdout. Errors to stderr only.

**Dirty queue entry format:**

```json
{ "path": "src/auth.py", "artifact_type": "code", "queued_at": "2026-09-24T10:00:00Z" }
```

**Artifact type inference:**

| Path pattern | Inferred artifact_type |
|---|---|
| Files under `specs/`, `spec/`, or matching `*.spec.*` | `spec` |
| Files matching doc extensions (`.md`, `.rst`, `.txt`, `.adoc`, `.docx`, `.pptx`, `.pdf`) | `doc` |
| All other files | `code` |

Artifact type inference is configurable via `ingestion.spec_patterns` and `ingestion.doc_watch_patterns` in `cartographer.toml`.

**Failure handling:** If the dirty queue file cannot be written (permissions, disk full), log to stderr and exit `0`. Do not surface errors to the user during a coding turn.

---

### 5.2 Ingest flush (`Stop`)

**Event:** `Stop` (end of Claude turn). Also triggered by a git post-commit hook when `topology.promotion_trigger = "post-merge-hook"`.

**Purpose:** Drain the dirty queue and ingest all queued files into the local VDB and KG.

**Contract:**
- Input: the dirty queue at `$CLAUDE_PROJECT_DIR/.cartographer/dirty_queue.jsonl`.
- Operation:
  1. Read and lock the dirty queue.
  2. If empty: exit `0` immediately.
  3. Deduplicate entries by path (keep the most recent `queued_at` per path).
  4. For each file:
     a. Determine artifact type from queue entry.
     b. Extract text (plain files: read directly; binary: invoke Claude via MCP).
     c. Chunk, embed, extract graph.
     d. `vdb_upsert` to local scope.
     e. `kg_upsert_nodes` and `kg_upsert_edges` to local scope.
  5. Clear the dirty queue on success.
  6. Update `last_indexed_at` in the registry.
- Output: nothing to stdout. Log ingestion summary to `~/.cartographer/cli.log`.

**Debounce:** The flush script checks the age of the newest entry in the dirty queue. If the newest entry is less than `ingestion.debounce_seconds` old, the flush defers and exits `0`. This prevents the flush from running mid-burst when the developer is editing multiple files rapidly. The next `Stop` event will pick it up.

**Failure handling:**

| Failure | Behavior |
|---|---|
| A single file fails to ingest | Log the file path and error, continue with remaining files |
| Embedder unavailable | Log error, leave dirty queue intact for next flush, exit `0` |
| VDB or KG write fails | Log error, leave dirty queue intact for next flush, exit `0` |
| Binary file extraction fails (Claude unavailable) | Log file path, skip, continue |

Dirty queue entries are only cleared after all entries have been processed successfully. If any entry fails, the queue retains the failed entries for the next flush.

---

### 5.3 Preload (`SessionStart`)

**Event:** `SessionStart` (once per Claude Code session open).

**Purpose:** Inject a scoped context slice into session context, covering the current branch and working set. Write session metadata to `$CLAUDE_ENV_FILE` for use by subsequent hooks.

**Contract:**
- Input: `$CLAUDE_PROJECT_DIR` and `$CLAUDE_ENV_FILE` from the Claude Code environment.
- Operation:
  1. Load `cartographer.toml` for the project at `$CLAUDE_PROJECT_DIR`.
  2. Write to `$CLAUDE_ENV_FILE`: `project_id`, `local_path`, `central_endpoint` (if configured), and the dirty queue path.
  3. Determine the current working set: files modified on the current git branch since it diverged from main (`git diff --name-only main...HEAD`).
  4. `kg_neighbors` for each file in the working set (depth 1, local scope).
  5. `vdb_query` for top-k chunks most relevant to the working set file paths (local scope first, then global if configured).
  6. Format results as a compact context block within `recall.preload_budget_tokens`.
  7. Write the context block to stdout (injected into session context by Claude Code).
- Output: formatted context block to stdout, within the configured token budget.

**Context block format:**

```
[Cartographer: session context]
Project: <name> (<project_id>)
Working set: <n> files on branch <branch_name>

Relevant prior knowledge:
- <path>#<symbol> (<origin>): <first line of chunk text>
  ...

Related graph neighbors:
- <node_id> (<node_type>): <name> — <edge_type> -> <dst_id>
  ...
[end Cartographer context]
```

**Token budget enforcement:** If the formatted block exceeds `recall.preload_budget_tokens`, truncate by dropping lowest-scored VDB results first, then lowest-distance KG neighbors.

**Failure handling:** If any step fails (config not found, backend unavailable, git not initialized), the hook exits `0` silently. A failed preload is not fatal. It must never block a session from opening.

---

### 5.4 Retrieve (`UserPromptSubmit`)

**Event:** `UserPromptSubmit` (before each user prompt is submitted to Claude).

**Purpose:** Inject per-turn relevant knowledge based on the current prompt text.

**Contract:**
- Input: the prompt text submitted by the user, read from the `UserPromptSubmit` payload. Session metadata from `$CLAUDE_ENV_FILE` (written by preload).
- Operation:
  1. Read session metadata from `$CLAUDE_ENV_FILE`. If not present (preload did not run): fall back to loading config from `$CLAUDE_PROJECT_DIR`.
  2. `vdb_query(text=prompt, k=recall.top_k_vdb, scope=local)`.
  3. If central topology: `vdb_query(text=prompt, k=recall.top_k_vdb, scope=global)`.
  4. Merge results, deduplicate by artifact identity, tag by origin.
  5. `kg_neighbors` for the top 3 VDB results (depth 1, matching scope).
  6. Format within `recall.per_turn_budget_tokens`.
  7. Write formatted context block to stdout.
- Output: formatted context block to stdout, prepended to the prompt.

**Token budget enforcement:** Same truncation strategy as preload: drop lowest-scored VDB results first, then KG neighbors.

**Failure handling:** Same as preload. A failed retrieve must never block a prompt from being submitted. Exit `0` silently on any error.

---

## 6. Cowork Desktop limitation

Plugin hooks do not fire in Claude Code Cowork Desktop sessions. Cowork restricts settings resolution to user scope only; project-scope hooks (which is how Cartographer's hooks are registered) are not executed.

Skills, slash commands, and MCP servers from the same plugin still work in Cowork sessions. Only the always-on hooks (ingest, preload, retrieve) are affected.

**Impact:** In Cowork sessions, the knowledge layer is not updated automatically and relevant knowledge is not injected into context. Developers using Cowork must run `cartographer seed` manually and use the recall skill explicitly.

This limitation must be documented prominently in the project README and the onboarding instructions for any team that uses Cowork.

---

## 7. Testing hooks locally

```bash
# Test the enqueue hook manually
echo '{"tool": "Write", "path": "src/auth.py"}' | \
  CLAUDE_PROJECT_DIR=$(pwd) \
  python cartographer-plugin/scripts/ingest_enqueue.py

# Test the flush hook manually
CLAUDE_PROJECT_DIR=$(pwd) \
  python cartographer-plugin/scripts/ingest_flush.py

# Test the preload hook manually
CLAUDE_PROJECT_DIR=$(pwd) \
CLAUDE_ENV_FILE=/tmp/carto_test_env.sh \
  python cartographer-plugin/scripts/preload.py
```

Use `cartographer doctor` to verify that hooks are registered correctly in `.claude/settings.json` and that the scripts are reachable via `${CLAUDE_PLUGIN_ROOT}`.

---

*For the MCP tool contracts the flush and retrieve hooks call, see [contracts/vdb-tools.md](../contracts/vdb-tools.md) and [contracts/kg-tools.md](../contracts/kg-tools.md). For the MCP server definitions, see [mcp-servers.md](mcp-servers.md).*
