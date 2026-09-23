"""Detect and additively merge into existing Claude Code configuration.

Per PROJECT_BRIEF.md Section 6.1 "Setup rules": never clobber. If CLAUDE.md,
.claude/settings.json, or .mcp.json exist, back them up, then merge additively and
dedupe MCP entries. Report every change.

`init`'s current additions to settings.json / .mcp.json are empty ({}), because
those files are where the Cartographer *plugin's* hooks and MCP server entries would
be registered, and the plugin package is separate, later work (not built in this
CLI-only slice). The merge machinery here is real and tested; there is just nothing
to add yet. CLAUDE.md is different: Cartographer owns a pointer to the standards
baseline today, so that file is always created/updated.
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
## Cartographer

This project uses Cartographer for development standards and a persistent local
knowledge index. Standards live under `.claude/standards/`. Project config is in
`cartographer.toml`. Do not edit the content between these markers by hand; run
`cartographer init` or `cartographer stack add <name>` instead.
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
            action="unchanged",
            detail="no Cartographer plugin entries to add yet, so init leaves this file alone "
            "(plugin not installed)",
        )
    )

    mcp_json = workspace / MCP_JSON_NAME
    entries.append(
        DetectionEntry(
            name=MCP_JSON_NAME,
            path=mcp_json,
            exists=mcp_json.exists(),
            action="unchanged",
            detail="no Cartographer MCP servers to add yet, so init leaves this file alone "
            "(plugin not installed)",
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


def ensure_claude_md(workspace: Path) -> tuple[Path, bool]:
    """Create or additively update CLAUDE.md. Returns (path, changed)."""
    path = workspace / CLAUDE_MD_NAME
    if not path.exists():
        path.write_text(f"# Project instructions\n\n{CARTOGRAPHER_CLAUDE_MD_BLOCK}", encoding="utf-8")
        return path, True

    text = path.read_text(encoding="utf-8")
    if BEGIN_MARKER in text:
        return path, False

    backup(path, workspace)
    separator = "\n\n" if not text.endswith("\n\n") else ""
    path.write_text(text + separator + CARTOGRAPHER_CLAUDE_MD_BLOCK, encoding="utf-8")
    return path, True


def deep_merge_settings(existing: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two settings.json-shaped dicts. `additions` wins on scalar
    conflicts; lists are concatenated and deduped by value; dicts recurse."""
    merged = copy.deepcopy(existing)
    for key, value in additions.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
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
