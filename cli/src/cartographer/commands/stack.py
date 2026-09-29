"""`cartographer stack add <name>`: apply a bundled standards pack into a workspace."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod
from cartographer.ingestion import parsers as parser_registry

app = typer.Typer(help="Manage standards packs.")
console = Console()

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


def _copy_to_agents_dir(src_dir: Path, agents_dest: Path) -> list[Path]:
    """Idempotently copy all .md files from src_dir into .claude/agents/."""
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


def apply_pack(workspace: Path, name: str) -> tuple[list[Path], list[Path]]:
    """Install a standards pack plus its skills and agents into the workspace.

    Copies:
    - standards  → .claude/standards/<name>/
    - core skills + agents (always) → .claude/agents/
    - stack-specific skills + agents → .claude/agents/

    Returns (standards_written, agents_written). Idempotent.
    """
    # Standards
    src_dir = _bundled_pack_dir(name)
    dest_dir = workspace / ".claude" / "standards" / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    standards_written: list[Path] = []
    for src_file in sorted(src_dir.glob("*.md")):
        dest_file = dest_dir / src_file.name
        content = src_file.read_bytes()
        if dest_file.exists() and dest_file.read_bytes() == content:
            continue
        dest_file.write_bytes(content)
        standards_written.append(dest_file)

    # Skills and agents → .claude/agents/
    agents_dest = workspace / ".claude" / "agents"
    agents_written: list[Path] = []

    for top in ("skills_packs", "agents_packs"):
        for pack_name in ("core", name):
            src = _optional_bundled_dir(top, pack_name)
            if src:
                agents_written.extend(_copy_to_agents_dir(src, agents_dest))

    return standards_written, agents_written


@app.command("add")
def add(
    name: str = typer.Argument(..., help="Stack pack name, e.g. python or react"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    standards_written, agents_written = apply_pack(workspace, name)
    written = standards_written + agents_written

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
        f"stack '{name}': {len(standards_written)} standard(s) → .claude/standards/{name}/, "
        f"{len(agents_written)} skill(s)/agent(s) → .claude/agents/"
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
