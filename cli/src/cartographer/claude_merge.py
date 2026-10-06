"""Detect and additively merge into existing Claude Code configuration.

Per PROJECT_BRIEF.md Section 6.1 "Setup rules": never clobber. If CLAUDE.md,
.claude/settings.json, or .mcp.json exist, back them up, then merge additively and
dedupe MCP entries. Report every change.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLAUDE_MD_NAME = "CLAUDE.md"
SETTINGS_JSON_REL = Path(".claude") / "settings.json"
MCP_JSON_NAME = ".mcp.json"
BACKUP_DIR_REL = Path(".claude") / ".cartographer-backup"

BEGIN_MARKER = "<!-- BEGIN CARTOGRAPHER -->"
END_MARKER = "<!-- END CARTOGRAPHER -->"

CARTOGRAPHER_CLAUDE_MD_BLOCK = f"""{BEGIN_MARKER}
## Cartographer knowledge index

This project has a persistent knowledge index. **VDB and KG are your primary search tools for every codebase task — understanding, editing, reviewing, or planning.** Use them before opening any file.

### Mandatory protocol — follow this order on every task

1. **VDB first** — call `vdb_search` with a query about the concept, symbol, or feature you need. It returns the most relevant files and excerpts ranked by semantic relevance.
2. **KG next** — use `kg_query` to trace callers, importers, dependents, and spec relationships from the files VDB returned.
3. **Read only what they point to** — open files with `Read` only after VDB or KG has identified them as relevant. Never open a file speculatively.

**Hard rules — these override default behavior:**
- Never run `grep`, `find`, or `Glob` to locate files or understand codebase structure. Ask the VDB instead — it searches everything semantically.
- Never read a file that VDB or KG has not first confirmed is relevant to the task.
- Never read a whole directory or module to get oriented. Search first, read the specific files the search returns.
- Exception: pattern-specific scans that VDB cannot do (finding all empty catch blocks, hardcoded credential patterns, running a linter) are acceptable *after* VDB/KG have established scope.

### MCP tools

- **cartographer-vdb** — semantic vector search over all indexed files, specs, and docs.
  Use for: finding files related to a concept, understanding what a module does,
  locating specs or decisions relevant to your task.

- **cartographer-kg** — knowledge graph queries (Cypher) over artifact relationships.
  Use for: finding what implements a spec, what calls a function, what imports a module,
  what extends a class, and traversing relationships between components.

  Available edge types on `RelatesTo`:
  - `calls` — function A calls function B (AST-derived, high confidence)
  - `imports` — file A imports file B (AST-derived, high confidence)
  - `extends` — class A extends class B (AST-derived, high confidence)
  - `defines` — file defines a symbol
  - `implements_spec` — code or doc references a spec
  - `depends_on` — semantic dependency (LLM-inferred, only present with --enrich)

  Example queries:
  ```
  MATCH (a:Artifact)-[r:RelatesTo {{type: 'calls'}}]->(b:Artifact)
  WHERE b.attrs CONTAINS 'my_function' RETURN a.path LIMIT 20

  MATCH (a:Artifact)-[r:RelatesTo {{type: 'extends'}}]->(b:Artifact)
  WHERE b.attrs CONTAINS 'BaseClass' RETURN a.path LIMIT 10
  ```

Standards live under `.claude/standards/`. Re-index after major changes with `cartographer seed`.
Do not edit the content between these markers by hand.
{END_MARKER}
"""

CARTOGRAPHER_CLAUDE_MD_BLOCK_NO_INDEX = f"""{BEGIN_MARKER}
## Cartographer standards

This project uses Cartographer's standards, skills, and agents packs, without the KG/VDB knowledge
index (`topology = "none"`). Standards live under `.claude/standards/`.

Skills and agents that reference KG/VDB lookups (`vdb_search`, `kg_query`, `kg_neighbors`) won't have
those tools available in this project -- fall back to `Read`/`Grep`/`Glob` for anything they'd
otherwise have looked up.

Do not edit the content between these markers by hand.
{END_MARKER}
"""


@dataclass
class DetectionEntry:
    name: str
    path: Path
    exists: bool
    action: str  # "create" | "merge" | "unchanged"
    detail: str


def detect(workspace: Path) -> list[DetectionEntry]:
    """Read-only report of what `init` would create versus merge. No writes."""
    entries: list[DetectionEntry] = []

    claude_md = workspace / CLAUDE_MD_NAME
    if claude_md.exists():
        already_has_block = BEGIN_MARKER in claude_md.read_text(encoding="utf-8")
        entries.append(
            DetectionEntry(
                name=CLAUDE_MD_NAME,
                path=claude_md,
                exists=True,
                action="unchanged" if already_has_block else "merge",
                detail="Cartographer section already present" if already_has_block
                else "would back up and append a Cartographer section",
            )
        )
    else:
        entries.append(
            DetectionEntry(
                name=CLAUDE_MD_NAME,
                path=claude_md,
                exists=False,
                action="create",
                detail="would create with a Cartographer section",
            )
        )

    settings_json = workspace / SETTINGS_JSON_REL
    entries.append(
        DetectionEntry(
            name=str(SETTINGS_JSON_REL),
            path=settings_json,
            exists=settings_json.exists(),
            action="merge" if settings_json.exists() else "create",
            detail="would merge Cartographer hook entries (PostToolUse, Stop, SessionStart, UserPromptSubmit)",
        )
    )

    mcp_json = workspace / MCP_JSON_NAME
    entries.append(
        DetectionEntry(
            name=MCP_JSON_NAME,
            path=mcp_json,
            exists=mcp_json.exists(),
            action="merge" if mcp_json.exists() else "create",
            detail="would add cartographer-vdb and cartographer-kg MCP server entries",
        )
    )

    return entries


def backup(path: Path, workspace: Path) -> Path | None:
    """Copy an existing file into .claude/.cartographer-backup/ with a timestamp
    suffix. Returns None if the source file does not exist yet."""
    if not path.exists():
        return None
    backup_dir = workspace / BACKUP_DIR_REL
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{path.name}.{timestamp}.bak"
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def ensure_claude_md(workspace: Path, block: str = CARTOGRAPHER_CLAUDE_MD_BLOCK) -> tuple[Path, bool]:
    """Create or additively update CLAUDE.md. Returns (path, changed).

    `block` defaults to the standard VDB/KG-mandatory block; callers with
    indexing disabled (topology="none") pass CARTOGRAPHER_CLAUDE_MD_BLOCK_NO_INDEX
    instead, which drops the VDB/KG mandate (there's no index behind it) but
    keeps the standards pointer.
    """
    path = workspace / CLAUDE_MD_NAME
    if not path.exists():
        path.write_text(f"# Project instructions\n\n{block}", encoding="utf-8")
        return path, True

    text = path.read_text(encoding="utf-8")
    if BEGIN_MARKER in text and END_MARKER in text:
        # Replace the existing block in-place so content stays current
        start = text.index(BEGIN_MARKER)
        end = text.index(END_MARKER) + len(END_MARKER)
        existing_block = text[start:end]
        new_block = block.strip()
        if existing_block == new_block:
            return path, False
        backup(path, workspace)
        path.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
        return path, True

    backup(path, workspace)
    separator = "\n\n" if not text.endswith("\n\n") else ""
    path.write_text(text + separator + block, encoding="utf-8")
    return path, True


def _has_cartographer_command(hook_group: Any) -> bool:
    """Return True if a hook group dict contains any 'cartographer hook' command."""
    if not isinstance(hook_group, dict):
        return False
    for hook in hook_group.get("hooks", []):
        if isinstance(hook, dict) and "cartographer hook" in hook.get("command", ""):
            return True
    return False


def deep_merge_settings(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two settings.json-shaped dicts. `additions` wins on scalar
    conflicts; hook lists evict old Cartographer entries before appending new ones;
    other lists are concatenated and deduped by value; dicts recurse."""
    merged = copy.deepcopy(existing)
    for key, value in additions.items():
        # This must come before the generic dict-recursion branch below: once
        # "hooks" exists as a dict in `merged` (i.e. every run after the first),
        # that branch's condition also matches "hooks" and would run a plain
        # recursive dict-merge instead — the per-event lists would then fall
        # into the generic list-concat branch on the *recursive* call, silently
        # skipping the Cartographer-entry eviction below. Order-dependent; this
        # branch order is load-bearing, not incidental.
        if key == "hooks" and isinstance(merged.get(key), dict) and isinstance(value, dict):
            # Per-event hook lists: evict stale Cartographer entries before adding new ones
            merged_hooks = copy.deepcopy(merged[key])
            for event, event_hooks in value.items():
                existing_event = [h for h in merged_hooks.get(event, []) if not _has_cartographer_command(h)]
                merged_hooks[event] = existing_event + [h for h in event_hooks if h not in existing_event]
            merged[key] = merged_hooks
        elif key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_settings(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            combined = merged[key] + [item for item in value if item not in merged[key]]
            merged[key] = combined
        else:
            merged[key] = value
    return merged


def merge_mcp_servers(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Merge `.mcp.json`-shaped dicts, deduping the `mcpServers` map by server name."""
    merged = copy.deepcopy(existing)
    servers = merged.get("mcpServers", {})
    for name, server_def in additions.get("mcpServers", {}).items():
        servers[name] = server_def
    if servers:
        merged["mcpServers"] = servers
    return merged


def _ensure_json(path: Path, workspace: Path, additions: dict[str, Any], merge_fn) -> tuple[Path, bool]:
    if not additions and path.exists():
        return path, False

    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        merged = merge_fn(existing, additions)
        if merged == existing:
            return path, False
        backup(path, workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        return path, True

    if not additions:
        return path, False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(additions, indent=2) + "\n", encoding="utf-8")
    return path, True


def ensure_settings_json(workspace: Path, additions: dict[str, Any] | None = None) -> tuple[Path, bool]:
    path = workspace / SETTINGS_JSON_REL
    return _ensure_json(path, workspace, additions or {}, deep_merge_settings)


def ensure_mcp_json(workspace: Path, additions: dict[str, Any] | None = None) -> tuple[Path, bool]:
    path = workspace / MCP_JSON_NAME
    return _ensure_json(path, workspace, additions or {}, merge_mcp_servers)
