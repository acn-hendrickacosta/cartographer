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


def _mcp_servers(workspace: Path) -> dict:
    """Return .mcp.json content using HTTP transport with workspace in the URL.

    Enterprise environments often block stdio MCP servers. We use HTTP localhost
    instead — one global `cartographer serve` handles all projects. The workspace
    path is passed as a query parameter so the server routes each request to the
    correct index without needing a separate server instance per project.
    """
    from cartographer.commands.serve import VDB_DEFAULT_PORT, KG_DEFAULT_PORT
    ws = str(workspace)
    return {
        "mcpServers": {
            "cartographer-vdb": {
                "url": f"http://localhost:{VDB_DEFAULT_PORT}/mcp?workspace={ws}",
            },
            "cartographer-kg": {
                "url": f"http://localhost:{KG_DEFAULT_PORT}/mcp?workspace={ws}",
            },
        }
    }


def _hooks() -> dict:
    """Wire the four Claude Code hooks that keep the local index current
    automatically — PostToolUse enqueues changed files, Stop flushes them into
    the VDB/KG, SessionStart preloads context, UserPromptSubmit retrieves
    per-turn context. Without this, nothing ever re-ingests edited files; the
    project's design principle is deterministic hooks, not remembering to run
    `cartographer seed` by hand.

    No absolute paths needed: `cartographer` is on PATH after install, and
    Claude Code sets CLAUDE_PROJECT_DIR for every hook invocation, which the
    runtime scripts read via runtime.scripts.resolve_workspace().
    """
    return {
        "hooks": {
            "PostToolUse": [{
                "matcher": "Write|Edit|MultiEdit",
                "hooks": [{"type": "command", "command": "cartographer hook enqueue"}],
            }],
            "Stop": [{
                "hooks": [{"type": "command", "command": "cartographer hook flush"}],
            }],
            "SessionStart": [{
                "hooks": [{"type": "command", "command": "cartographer hook preload"}],
            }],
            "UserPromptSubmit": [{
                "hooks": [{"type": "command", "command": "cartographer hook retrieve"}],
            }],
        }
    }


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root to initialize"),
    stacks: str = typer.Option("", "--stacks", help="Comma-separated stack packs, e.g. python,react"),
    topology: str = typer.Option("", "--topology", help="local or central (default: preserve existing, or 'local' for new projects)"),
    name: str = typer.Option("", "--name", help="Project name; defaults to the workspace directory name"),
) -> None:
    workspace = path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    project_name = name or workspace.name

    # Resolve topology: explicit flag wins; otherwise preserve what's already in cartographer.toml;
    # fall back to "local" for brand-new projects.
    if not topology:
        if config_mod.config_exists(workspace):
            try:
                existing_cfg = config_mod.load_config(workspace)
                topology = existing_cfg.topology.mode
            except Exception:
                topology = "local"
        else:
            topology = "local"

    if topology not in ("local", "central"):
        raise typer.BadParameter("topology must be 'local' or 'central'")

    console.print(f"[bold]cartographer init[/bold] at {workspace}")

    _, claude_md_changed = claude_merge.ensure_claude_md(workspace)
    console.print(f"  CLAUDE.md: {'updated' if claude_md_changed else 'already up to date'}")

    _, settings_changed = claude_merge.ensure_settings_json(workspace, _hooks())
    console.print(f"  .claude/settings.json: {'updated' if settings_changed else 'already up to date'}")

    _, mcp_changed = claude_merge.ensure_mcp_json(workspace, _mcp_servers(workspace))
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

    # Always ensure the local override file exists and has a promotion token when
    # topology is central — even if the file already exists (re-running init).
    import secrets
    override = config_mod.load_local_override(workspace)
    local_cfg_existed = config_mod.local_config_path(workspace).exists()
    changed = False
    if topology == "central" and not override.promotion_token:
        override.promotion_token = secrets.token_hex(32)
        changed = True
    if not local_cfg_existed or changed:
        config_mod.save_local_override(workspace, override)
        action = "written" if not local_cfg_existed else "updated (promotion_token added)"
        console.print(f"  {config_mod.LOCAL_CONFIG_FILENAME} {action}")
    else:
        console.print(f"  {config_mod.LOCAL_CONFIG_FILENAME} already up to date")

    if topology == "central":
        console.print(
            rf"  [yellow]central topology: fill in \[central_vdb] and \[central_kg] "
            rf"credentials in {config_mod.LOCAL_CONFIG_FILENAME}[/yellow]"
        )
        try:
            import psycopg2  # noqa: F401
            import neo4j  # noqa: F401
        except ImportError:
            console.print(
                "  [red]central deps not installed — run:[/red]\n"
                "  uv pip install \"psycopg2-binary>=2.9\" \"neo4j>=5.0\" \\\n"
                "    --python \"$(pipx environment --value PIPX_LOCAL_VENVS)/cartographer/bin/python3\" -q\n"
                r"  or: pip install 'cartographer\[central]'"
            )

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
    """Copy SKILL.md files from the bundled plugin into .claude/commands/.

    Claude Code reads custom slash commands from .claude/commands/<name>.md; the
    file name becomes the /<name> command. Idempotent: overwrites with the latest version.
    """
    from cartographer.runtime import SKILLS_DIR

    skills_dest = workspace / ".claude" / "commands"
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
    # These files contain machine-specific absolute paths generated by `cartographer init`.
    # Each developer runs init after cloning; only cartographer.toml and CLAUDE.md are committed.
    required = [
        config_mod.LOCAL_CONFIG_FILENAME,
        str(LOCAL_INDEX_REL) + "/",
        ".mcp.json",
        ".claude/settings.json",
    ]
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [entry for entry in required if entry not in lines]
    if not missing:
        return
    lines.extend(missing)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
