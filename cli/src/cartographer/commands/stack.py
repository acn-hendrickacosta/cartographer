"""`cartographer stack add <name>`: apply a bundled standards pack into a workspace.

Also `stack fork`/`stack push` (SR.5): let a project copy a pack into its own
namespace in the Standards Registry and push local edits back to it. See
docs/phases/sr-5-project-forks.md.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod, standards_registry
from cartographer.ingestion import parsers as parser_registry

app = typer.Typer(help="Manage standards packs.")
console = Console()

# Tracks, per content type and pack name, which currently-installed files
# came from that pack -- needed because .claude/skills/ and .claude/agents/
# are shared, multi-pack-merged directories with no other record of
# provenance once installed (unlike .claude/standards/<pack>/, which is
# already pack-isolated). `stack push` reads this to know exactly which
# on-disk files to zip up for a given pack. Written/updated by apply_pack
# on every run; never read by apply_pack itself.
PROVENANCE_REL = Path(".cartographer") / "pack_provenance.json"

KNOWN_PACKS = (
    "cross-stack",
    "python",
    "react",
    "typescript",
    "golang",
    "rust",
    "java",
    "kotlin",
    "angular",
    "vue",
    "swift",
    "dart",
)


def _bundled_pack_dir(name: str) -> Path:
    pack_dir = resources.files("cartographer").joinpath("standards_packs", name)
    if not pack_dir.is_dir():
        raise typer.BadParameter(
            f"unknown stack pack '{name}', known packs: {', '.join(KNOWN_PACKS)}"
        )
    return Path(str(pack_dir))


def _optional_bundled_dir(top: str, name: str) -> Path | None:
    """Return the path for a skills or agents sub-pack, or None if it doesn't exist."""
    d = resources.files("cartographer").joinpath(top, name)
    p = Path(str(d))
    return p if p.is_dir() else None


def _install_skills_pack(src_dir: Path, skills_root: Path, commands_dir: Path) -> list[Path]:
    """Idempotently install skill files into .claude/skills/<name>/SKILL.md.

    Claude Code auto-loads skills from this structure based on each skill's
    description frontmatter, and also exposes them as /<name> slash commands.

    Also removes any stale flat copies from .claude/commands/ left by older
    versions of Cartographer that used the legacy commands format.
    """
    written: list[Path] = []
    for src_file in sorted(src_dir.glob("*.md")):
        skill_name = src_file.stem
        skill_dir = skills_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        dest_file = skill_dir / "SKILL.md"
        content = src_file.read_bytes()
        if not (dest_file.exists() and dest_file.read_bytes() == content):
            dest_file.write_bytes(content)
            written.append(dest_file)
        # Remove stale legacy copy from .claude/commands/ if present
        legacy = commands_dir / src_file.name
        if legacy.exists():
            legacy.unlink()
    return written


def _install_agents_pack(src_dir: Path, agents_dest: Path) -> list[Path]:
    """Idempotently copy agent definition files into .claude/agents/."""
    agents_dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for src_file in sorted(src_dir.glob("*.md")):
        dest_file = agents_dest / src_file.name
        content = src_file.read_bytes()
        if dest_file.exists() and dest_file.read_bytes() == content:
            continue
        dest_file.write_bytes(content)
        written.append(dest_file)
    return written


def _apply_bundled_standards(src_dir: Path, dest_dir: Path) -> list[Path]:
    written: list[Path] = []
    for src_file in sorted(src_dir.glob("*.md")):
        dest_file = dest_dir / src_file.name
        content = src_file.read_bytes()
        if dest_file.exists() and dest_file.read_bytes() == content:
            continue
        dest_file.write_bytes(content)
        written.append(dest_file)
    return written


def _fetch_registry_content(
    registry_url: str,
    registry_fallback: str,
    registry_token: str,
    pack_name: str,
    content_type: str,
    extractor,
    dest_dir: Path,
) -> tuple[bool, list[Path]]:
    """Attempt a registry fetch for one (pack_name, content_type) pair.

    Returns (fetched, written). fetched=False means "fall back to bundled".
    A 404 (this pack genuinely has no content of this type -- common and
    expected, e.g. 'angular' has no stack-specific agents) is always a silent
    fallback, regardless of registry_fallback -- it's not an operational
    problem. Any other failure (bad token, network, 5xx) respects
    registry_fallback: "warn" logs and falls back, "error" exits 1.
    """
    try:
        version, zip_bytes = standards_registry.fetch_pack_content(
            registry_url, pack_name, content_type, registry_token
        )
        written = extractor(zip_bytes, dest_dir)
        console.print(f"  '{pack_name}' {content_type}: fetched v{version} from registry ({registry_url})")
        return True, written
    except standards_registry.RegistryContentNotFoundError:
        return False, []
    except standards_registry.RegistryFetchError as exc:
        if registry_fallback == "error":
            console.print(f"[red]FAIL[/red] registry fetch failed for '{pack_name}' {content_type}: {exc}")
            raise typer.Exit(code=1) from exc
        console.print(
            f"[yellow]warning[/yellow]: registry fetch failed for '{pack_name}' {content_type} ({exc}); "
            "using bundled version"
        )
        return False, []


def _resolve_registry_settings(workspace: Path) -> tuple[str, str, str]:
    """Read stacks.registry_url / registry_fallback from cartographer.toml, and
    registry_token from cartographer.local.toml, if they exist yet. A brand-new
    `init` calls apply_pack before cartographer.toml is written (see init.py) --
    config_exists is False there, so this returns ("", "warn", "") and the
    bundled path below is used, same as today's behavior. A re-run of
    `init --stack` or `stack add` on an already-configured project picks up
    whatever registry_url/registry_token is already committed/configured."""
    if not config_mod.config_exists(workspace):
        return "", "warn", ""
    try:
        cfg = config_mod.load_config(workspace)
    except Exception:
        return "", "warn", ""
    override = config_mod.load_local_override(workspace)
    return cfg.stacks.registry_url, cfg.stacks.registry_fallback, override.registry_token


def _load_provenance_manifest(workspace: Path) -> dict[str, dict[str, list[str]]]:
    path = workspace / PROVENANCE_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _update_provenance_manifest(workspace: Path, provenance: dict[str, dict[str, list[str]]]) -> None:
    """Merges `provenance` (this run's {content_type: {pack_name: [files]}})
    into the on-disk manifest, leaving other packs' entries (from earlier
    `apply_pack` runs) untouched."""
    path = workspace / PROVENANCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_provenance_manifest(workspace)
    for content_type, by_pack in provenance.items():
        data.setdefault(content_type, {}).update(by_pack)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def apply_pack(workspace: Path, name: str) -> tuple[list[Path], list[Path], list[Path]]:
    """Install a standards pack plus its skills and agents into the workspace.

    All three content types are fetched from the Standards Registry when
    stacks.registry_url is configured, falling back independently to the
    bundled version per stacks.registry_fallback on fetch failure -- "the
    registry has no content of this type for this pack" (e.g. 'angular' has
    no stack-specific agents) and "the fetch failed" are both treated as
    fall-back-to-bundled, not errors, unless registry_fallback == "error".

    - standards → .claude/standards/<name>/*.md (flat)
    - core skills + stack skills → .claude/skills/<skill-name>/SKILL.md (auto-loaded by Claude;
      registry archives preserve the <skill-name>/ subdirectory, see extract_skills_zip)
    - core agents + stack agents → .claude/agents/<agent-name>.md (flat)

    Returns (standards_written, skills_written, agents_written). Idempotent for
    the bundled path; registry-fetched content always overwrites.
    """
    registry_url, registry_fallback, registry_token = _resolve_registry_settings(workspace)
    provenance: dict[str, dict[str, list[str]]] = {"standards": {}, "skills": {}, "agents": {}}

    # Standards → .claude/standards/<name>/
    src_dir = _bundled_pack_dir(name)  # also validates name against KNOWN_PACKS
    dest_dir = workspace / ".claude" / "standards" / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    standards_written: list[Path] = []
    fetched = False
    if registry_url:
        fetched, standards_written = _fetch_registry_content(
            registry_url, registry_fallback, registry_token, name, "standards",
            standards_registry.extract_pack_zip, dest_dir,
        )
    if not fetched:
        standards_written = _apply_bundled_standards(src_dir, dest_dir)
    # .claude/standards/<name>/ is already pack-isolated, so the complete
    # membership is just whatever's in it now -- unlike skills/agents below,
    # no need to distinguish "written this run" from "already there".
    provenance["standards"][name] = sorted(p.name for p in dest_dir.glob("*.md"))

    # Skills → .claude/skills/<skill-name>/SKILL.md, from both "core" and this stack's own pack
    skills_root = workspace / ".claude" / "skills"
    commands_dir = workspace / ".claude" / "commands"
    skills_written: list[Path] = []
    for pack_name in ("core", name):
        fetched = False
        pack_skill_names: list[str] = []
        if registry_url:
            fetched, written = _fetch_registry_content(
                registry_url, registry_fallback, registry_token, pack_name, "skills",
                standards_registry.extract_skills_zip, skills_root,
            )
            skills_written.extend(written)
            if fetched:
                # extract_skills_zip always overwrites (no skip-if-unchanged),
                # so `written` is already the complete set for this pack.
                pack_skill_names = sorted({p.parent.name for p in written})
        if not fetched:
            src = _optional_bundled_dir("skills_packs", pack_name)
            if src:
                skills_written.extend(_install_skills_pack(src, skills_root, commands_dir))
                # _install_skills_pack skips already-matching files, so its
                # return value is incomplete -- the source dir's full
                # listing is the actual complete membership for this pack.
                pack_skill_names = sorted(p.stem for p in src.glob("*.md"))
        if pack_skill_names:
            provenance["skills"][pack_name] = pack_skill_names

    # Agents → .claude/agents/<agent-name>.md, from both "core" and this stack's own pack
    agents_dest = workspace / ".claude" / "agents"
    agents_written: list[Path] = []
    for pack_name in ("core", name):
        fetched = False
        pack_agent_names: list[str] = []
        if registry_url:
            fetched, written = _fetch_registry_content(
                registry_url, registry_fallback, registry_token, pack_name, "agents",
                standards_registry.extract_pack_zip, agents_dest,
            )
            agents_written.extend(written)
            if fetched:
                pack_agent_names = sorted(p.name for p in written)
        if not fetched:
            src = _optional_bundled_dir("agents_packs", pack_name)
            if src:
                agents_written.extend(_install_agents_pack(src, agents_dest))
                pack_agent_names = sorted(p.name for p in src.glob("*.md"))
        if pack_agent_names:
            provenance["agents"][pack_name] = pack_agent_names

    _update_provenance_manifest(workspace, provenance)
    return standards_written, skills_written, agents_written


@app.command("add")
def add(
    name: str = typer.Argument(..., help="Stack pack name, e.g. python or react"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    standards_written, skills_written, agents_written = apply_pack(workspace, name)

    if config_mod.config_exists(workspace):
        cfg = config_mod.load_config(workspace)
        if name not in cfg.stacks.active:
            cfg.stacks.active = sorted({*cfg.stacks.active, name})
            config_mod.save_config(workspace, cfg)
    else:
        console.print(
            f"[yellow]warning[/yellow]: no cartographer.toml at {workspace}; "
            "run 'cartographer init' first so active stacks are tracked"
        )

    console.print(
        f"stack '{name}': "
        f"{len(standards_written)} standard(s) → .claude/standards/{name}/, "
        f"{len(skills_written)} skill(s) → .claude/skills/, "
        f"{len(agents_written)} agent(s) → .claude/agents/"
    )

    hint = parser_registry.STACK_PARSER_HINTS.get(name)
    if hint:
        import_name, extra, filetypes, packages = hint
        if not parser_registry.is_parser_installed(import_name):
            cmd = parser_registry.install_hint(extra, packages)
            console.print(
                f"[yellow]note[/yellow]: '{name}' parses {filetypes} files with a regex fallback "
                f"until the real parser is installed (no calls/extends edges in the KG). Install with:\n"
                f"  {cmd}"
            )


@app.command("fork")
def fork(
    name: str = typer.Argument(..., help="Pack name to fork, e.g. python or core"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    """Fork a pack into this project's own namespace in the Standards Registry.

    One-time: from then on, this project's fetches for this pack (stack add /
    init --stack) transparently prefer the fork over the shared baseline, with
    no further config change needed -- the registry resolves this from the
    project's own bearer token. Use `stack push` to put local edits into the
    fork. Running `fork` again once one already exists is refused (409) --
    this does not "rebase" onto a newer baseline; see
    docs/phases/sr-5-project-forks.md.
    """
    workspace = path.resolve()
    registry_url, _, registry_token = _resolve_registry_settings(workspace)
    if not registry_url:
        console.print("[red]FAIL[/red] stacks.registry_url is not configured")
        raise typer.Exit(code=1)

    try:
        result = standards_registry.fork_pack(registry_url, name, registry_token)
    except standards_registry.RegistryFetchError as exc:
        console.print(f"[red]FAIL[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"forked '{name}' from baseline v{result['forked_from']} -- "
        "this project's future fetches/pushes for this pack now use the fork"
    )


def _push_content_type(
    registry_url: str, registry_token: str, pack_name: str, content_type: str, zip_bytes: bytes
) -> None:
    try:
        standards_registry.push_fork_content(registry_url, pack_name, content_type, zip_bytes, registry_token)
    except standards_registry.RegistryFetchError as exc:
        console.print(f"[red]FAIL[/red] pushing '{pack_name}' {content_type}: {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"  '{pack_name}' {content_type}: pushed to fork")


@app.command("push")
def push(
    name: str = typer.Argument(..., help="Pack name to push local changes for, e.g. python or core"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    """Push this project's current local content for a pack to its registry
    fork (must already exist -- run `cartographer stack fork <name>` first).

    Wholesale-replaces the fork's content per content type with whatever's
    currently installed on disk for that pack, using the provenance manifest
    apply_pack maintains (.cartographer/pack_provenance.json) to know exactly
    which installed files belong to this pack -- skills/agents live in a
    directory shared with other packs, so that manifest is what makes "push
    just this pack's files" possible. No SME review gate: this project's own
    bearer token is what already gates who can push.
    """
    workspace = path.resolve()
    registry_url, _, registry_token = _resolve_registry_settings(workspace)
    if not registry_url:
        console.print("[red]FAIL[/red] stacks.registry_url is not configured")
        raise typer.Exit(code=1)

    manifest = _load_provenance_manifest(workspace)
    pushed_any = False

    standards_files = manifest.get("standards", {}).get(name, [])
    if standards_files:
        zip_bytes = standards_registry.build_flat_zip(workspace / ".claude" / "standards" / name, standards_files)
        _push_content_type(registry_url, registry_token, name, "standards", zip_bytes)
        pushed_any = True

    skill_names = manifest.get("skills", {}).get(name, [])
    if skill_names:
        zip_bytes = standards_registry.build_skills_zip(workspace / ".claude" / "skills", skill_names)
        _push_content_type(registry_url, registry_token, name, "skills", zip_bytes)
        pushed_any = True

    agent_files = manifest.get("agents", {}).get(name, [])
    if agent_files:
        zip_bytes = standards_registry.build_flat_zip(workspace / ".claude" / "agents", agent_files)
        _push_content_type(registry_url, registry_token, name, "agents", zip_bytes)
        pushed_any = True

    if not pushed_any:
        console.print(
            f"[yellow]note[/yellow]: no installed content found for pack '{name}' -- nothing to push "
            "(run 'cartographer stack add' first so there's something on disk to push)"
        )
