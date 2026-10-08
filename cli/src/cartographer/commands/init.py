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
from cartographer.runtime import serve_state

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
    topology: str = typer.Option("", "--topology", help="local, central, or none (default: preserve existing, or 'local' for new projects)"),
    name: str = typer.Option("", "--name", help="Project name; defaults to the workspace directory name"),
    registry_url: str = typer.Option(
        "", "--registry-url", help="Standards Registry URL, e.g. http://localhost:8000 (default: preserve existing, or unset)"
    ),
    registry_token: str = typer.Option(
        "", "--registry-token",
        help="Per-project bearer token for the Standards Registry. Which pack content gets pulled "
             "(the shared baseline, or this project's own fork, if one exists) is determined entirely "
             "by this token -- never by a separate project name or id, so one project can't read "
             "another's fork just by knowing its name. Prefer the CARTO_REGISTRY_TOKEN env var over "
             "this flag where shell history/process-list exposure of secrets is a concern.",
    ),
) -> None:
    workspace = path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    project_name = name or workspace.name

    # Load the existing config (if any) as the base for everything init.py
    # doesn't explicitly own, so a re-run doesn't silently wipe fields set
    # outside of init (registry_url, retrieval tuning, taxonomy version,
    # federation overlays, etc.) -- this used to only special-case topology,
    # which meant every other section was reset to defaults on every re-run.
    existing_cfg: config_mod.CartographerConfig | None = None
    if config_mod.config_exists(workspace):
        try:
            existing_cfg = config_mod.load_config(workspace)
        except Exception:
            existing_cfg = None

    # Resolve topology: explicit flag wins; otherwise preserve what's already in cartographer.toml;
    # fall back to "local" for brand-new projects.
    if not topology:
        topology = existing_cfg.topology.mode if existing_cfg else "local"

    if topology not in ("local", "central", "none"):
        raise typer.BadParameter("topology must be 'local', 'central', or 'none'")
    indexing_enabled = topology != "none"

    console.print(f"[bold]cartographer init[/bold] at {workspace}")

    claude_md_block = (
        claude_merge.CARTOGRAPHER_CLAUDE_MD_BLOCK if indexing_enabled
        else claude_merge.CARTOGRAPHER_CLAUDE_MD_BLOCK_NO_INDEX
    )
    _, claude_md_changed = claude_merge.ensure_claude_md(workspace, block=claude_md_block)
    console.print(f"  CLAUDE.md: {'updated' if claude_md_changed else 'already up to date'}")

    _, settings_changed = claude_merge.ensure_settings_json(workspace, _hooks() if indexing_enabled else {})
    console.print(f"  .claude/settings.json: {'updated' if settings_changed else 'already up to date'}")

    _, mcp_changed = claude_merge.ensure_mcp_json(workspace, _mcp_servers(workspace) if indexing_enabled else {})
    console.print(f"  .mcp.json: {'updated' if mcp_changed else 'already up to date'}")

    if indexing_enabled:
        _install_skills(workspace)
        console.print("  skills: archaeology installed (project); recall installed (project + ~/.claude global)")
    else:
        console.print("  skills: archaeology/recall skipped (topology=none -- no index for them to use)")

    # Config (cartographer.toml + cartographer.local.toml) is written here, before the
    # apply_pack calls below -- specifically so --registry-url/--registry-token passed
    # to a brand-new init take effect on this same run. Previously a first-ever init
    # could never use the registry at all, since apply_pack ran before any config
    # existed on disk for _resolve_registry_settings to read (see its docstring in
    # commands/stack.py) -- only a second run could. A plain init with neither flag
    # behaves identically to before; this only changes when a config write that was
    # always going to happen anyway happens relative to apply_pack.
    project_id = compute_project_id(workspace)
    requested_stacks = [s.strip() for s in stacks.split(",") if s.strip()]
    active_stacks = sorted({"cross-stack", *requested_stacks})
    if existing_cfg:
        # Preserve everything init.py doesn't explicitly own. stacks.active is
        # the one StacksSection field init.py computes itself (from --stacks);
        # registry_fallback carries over from the existing config; registry_url
        # carries over too unless --registry-url overrides it below.
        cfg = existing_cfg.model_copy(deep=True)
        cfg.project = config_mod.ProjectSection(id=project_id, name=project_name)
        cfg.topology = config_mod.TopologySection(mode=topology)
        cfg.stacks.active = active_stacks
    else:
        cfg = config_mod.CartographerConfig(
            project=config_mod.ProjectSection(id=project_id, name=project_name),
            topology=config_mod.TopologySection(mode=topology),
            stacks=config_mod.StacksSection(active=active_stacks),
        )
    if registry_url:
        cfg.stacks.registry_url = registry_url
    config_mod.save_config(workspace, cfg)
    console.print(f"  {config_mod.CONFIG_FILENAME} written")

    # Always ensure the local override file exists and has a promotion token when
    # topology is central — even if the file already exists (re-running init).
    import secrets
    override = config_mod.load_local_override(workspace)
    local_cfg_existed = config_mod.local_config_path(workspace).exists()
    local_changed = False
    if topology == "central" and not override.promotion_token:
        override.promotion_token = secrets.token_hex(32)
        local_changed = True
    if registry_token and override.registry_token != registry_token:
        override.registry_token = registry_token
        local_changed = True
    if not local_cfg_existed or local_changed:
        config_mod.save_local_override(workspace, override)
        action = "written" if not local_cfg_existed else "updated"
        console.print(f"  {config_mod.LOCAL_CONFIG_FILENAME} {action}")
    else:
        console.print(f"  {config_mod.LOCAL_CONFIG_FILENAME} already up to date")

    if registry_token and not cfg.stacks.registry_url:
        console.print(
            "  [yellow]warning[/yellow]: --registry-token given but no registry_url configured "
            "(pass --registry-url too, or set stacks.registry_url in cartographer.toml) -- "
            "registry fetch will be skipped until it is"
        )

    apply_pack(workspace, "cross-stack")
    console.print("  standards + skills + agents: cross-stack baseline applied")

    for pack_name in requested_stacks:
        apply_pack(workspace, pack_name)
        console.print(f"  standards + skills + agents: {pack_name} pack applied")

    if indexing_enabled:
        local_dir = workspace / LOCAL_INDEX_REL
        vdb.ensure_collection(local_dir / "vdb.lance", scope="local")
        try:
            kg.ensure_namespace(local_dir / "kg.kuzu")
            console.print(f"  local index provisioned at {local_dir}")
        except RuntimeError as exc:
            # Kuzu's single-writer-per-file lock (see kg.py's _connect docstring)
            # means a second process can never open the KG read-write while
            # `cartographer serve` already holds it -- expected on any re-run of
            # `init` against a workspace serve is actively watching, not a real
            # failure: serve already owns schema creation/upkeep for this path.
            # Only swallow the error once we've confirmed serve is actually the
            # one holding the lock; otherwise this is a genuine problem (stale
            # lock file, disk issue, etc.) and should still surface.
            if "lock" in str(exc).lower() and serve_state.current_running_state() is not None:
                console.print(
                    f"  local index: KG schema check skipped -- 'cartographer serve' is already "
                    f"running and holds the write lock on {local_dir / 'kg.kuzu'} (it already owns "
                    "schema creation/upkeep for this workspace)"
                )
            else:
                raise
    else:
        console.print(
            "  local index: skipped (topology=none) -- existing .cartographer/local/, if any, is left untouched"
        )

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
    """Copy bundled SKILL.md files into .claude/skills/<name>/SKILL.md.

    Claude Code auto-loads skills from this structure based on each skill's
    description frontmatter, and also exposes them as /<name> slash commands.
    Idempotent: overwrites with the latest version.

    recall is also installed to ~/.claude/skills/recall/SKILL.md (user-level)
    so it is available in every Claude Code session on this machine, not just
    in Cartographer-initialized projects. Cross-project recall only makes sense
    as a global skill — the whole point is to query from any project context.

    archaeology stays project-level only: it bootstraps a specific project's
    index and has no meaningful use outside an initialized workspace.
    """
    from cartographer.runtime import SKILLS_DIR

    skills_root = workspace / ".claude" / "skills"
    commands_dir = workspace / ".claude" / "commands"

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            dest_dir = skills_root / skill_dir.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_md, dest_dir / "SKILL.md")
            # Remove stale legacy copy from .claude/commands/ if present
            legacy = commands_dir / f"{skill_dir.name}.md"
            if legacy.exists():
                legacy.unlink()

    # Install recall globally so it works from any project on this machine
    recall_src = SKILLS_DIR / "recall" / "SKILL.md"
    if recall_src.exists():
        global_recall_dir = Path.home() / ".claude" / "skills" / "recall"
        global_recall_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(recall_src, global_recall_dir / "SKILL.md")


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
