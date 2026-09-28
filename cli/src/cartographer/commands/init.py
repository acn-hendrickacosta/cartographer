"""`cartographer init`: scaffold the cross-stack baseline, apply stack packs,
provision the local index, write config, and register the project.

Idempotent by construction: every step it performs (CLAUDE.md merge, settings/mcp
merge, standards pack copy, index provisioning, config write, registry upsert) is
itself idempotent, per PROJECT_BRIEF.md Section 6.1.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console

from cartographer import claude_merge, config as config_mod, registry
from cartographer.artifact_id import compute_project_id
from cartographer.commands.stack import apply_pack
from cartographer.indexing import kg, vdb

console = Console()

LOCAL_INDEX_REL = Path(".cartographer") / "local"

# Hook entries written into .claude/settings.json.
# Uses `cartographer hook <name>` so no absolute path is needed — the cartographer
# binary is on PATH after pip install.
_HOOKS_SETTINGS = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Write|Edit|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "cartographer hook enqueue",
                    }
                ],
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "cartographer hook flush",
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "cartographer hook preload",
                    }
                ]
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "cartographer hook retrieve",
                    }
                ]
            }
        ],
    }
}

# MCP server entries written into .mcp.json.
# Uses the `cartographer-vdb-server` / `cartographer-kg-server` entry points
# installed on PATH by pyproject.toml [project.scripts].
_MCP_SERVERS = {
    "mcpServers": {
        "cartographer-vdb": {
            "command": "cartographer-vdb-server",
            "env": {"CARTO_WORKSPACE": "${workspaceFolder}"},
        },
        "cartographer-kg": {
            "command": "cartographer-kg-server",
            "env": {"CARTO_WORKSPACE": "${workspaceFolder}"},
        },
    }
}


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root to initialize"),
    stacks: str = typer.Option("", "--stacks", help="Comma-separated stack packs, e.g. python,react"),
    topology: str = typer.Option("local", "--topology", help="local or central"),
    name: str = typer.Option("", "--name", help="Project name; defaults to the workspace directory name"),
) -> None:
    if topology not in ("local", "central"):
        raise typer.BadParameter("topology must be 'local' or 'central'")

    workspace = path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    project_name = name or workspace.name

    console.print(f"[bold]cartographer init[/bold] at {workspace}")

    _, claude_md_changed = claude_merge.ensure_claude_md(workspace)
    console.print(f"  CLAUDE.md: {'updated' if claude_md_changed else 'already up to date'}")

    _, settings_changed = claude_merge.ensure_settings_json(workspace, _HOOKS_SETTINGS)
    console.print(f"  .claude/settings.json: {'updated' if settings_changed else 'already up to date'}")

    _, mcp_changed = claude_merge.ensure_mcp_json(workspace, _MCP_SERVERS)
    console.print(f"  .mcp.json: {'updated' if mcp_changed else 'already up to date'}")

    _install_skills(workspace)
    console.print("  skills: archaeology + recall installed")

    apply_pack(workspace, "cross-stack")
    console.print("  standards: cross-stack baseline applied")

    requested_stacks = [s.strip() for s in stacks.split(",") if s.strip()]
    for pack_name in requested_stacks:
        apply_pack(workspace, pack_name)
        console.print(f"  standards: {pack_name} pack applied")

    project_id = compute_project_id(workspace)
    local_dir = workspace / LOCAL_INDEX_REL
    vdb.ensure_collection(local_dir / "vdb.lance", scope="local")
    kg.ensure_namespace(local_dir / "kg.kuzu")
    console.print(f"  local index provisioned at {local_dir}")

    active_stacks = sorted({"cross-stack", *requested_stacks})
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name=project_name),
        topology=config_mod.TopologySection(mode=topology),
        stacks=config_mod.StacksSection(active=active_stacks),
    )
    config_mod.save_config(workspace, cfg)
    console.print(f"  {config_mod.CONFIG_FILENAME} written")

    if not config_mod.local_config_path(workspace).exists():
        config_mod.save_local_override(workspace, config_mod.LocalOverrideConfig())
        console.print(f"  {config_mod.LOCAL_CONFIG_FILENAME} written")

    _ensure_gitignore(workspace)

    record = registry.register_project(
        project_id=project_id,
        name=project_name,
        topology=topology,
        tenant=cfg.isolation.tenant,
        location=workspace,
    )
    console.print(f"  registered project {record.project_id} in {registry.registry_path()}")

    console.print("[bold green]init complete[/bold green]")


def _install_skills(workspace: Path) -> None:
    """Copy SKILL.md files from the bundled plugin into .claude/skills/.

    Claude Code reads skills from .claude/<skill-name>.md when the user invokes
    /<skill-name> in a session. Idempotent: overwrites with the latest version.
    """
    from cartographer.runtime import SKILLS_DIR

    skills_dest = workspace / ".claude" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            shutil.copy2(skill_md, skills_dest / f"{skill_dir.name}.md")


def _ensure_gitignore(workspace: Path) -> None:
    if not (workspace / ".git").exists():
        return
    gitignore = workspace / ".gitignore"
    required = [config_mod.LOCAL_CONFIG_FILENAME, str(LOCAL_INDEX_REL) + "/"]
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [entry for entry in required if entry not in lines]
    if not missing:
        return
    lines.extend(missing)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
