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

KNOWN_PACKS = ("cross-stack", "python", "react")


def _bundled_pack_dir(name: str) -> Path:
    pack_dir = resources.files("cartographer").joinpath("standards_packs", name)
    if not pack_dir.is_dir():
        raise typer.BadParameter(
            f"unknown stack pack '{name}', known packs: {', '.join(KNOWN_PACKS)}"
        )
    return Path(str(pack_dir))


def apply_pack(workspace: Path, name: str) -> list[Path]:
    """Copy a bundled standards pack into `.claude/standards/<name>/`.

    Idempotent: files whose content already matches are left untouched, so re-running
    `init` or `stack add` does not create noise in `git status`.
    """
    src_dir = _bundled_pack_dir(name)
    dest_dir = workspace / ".claude" / "standards" / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for src_file in sorted(src_dir.glob("*.md")):
        dest_file = dest_dir / src_file.name
        content = src_file.read_bytes()
        if dest_file.exists() and dest_file.read_bytes() == content:
            continue
        dest_file.write_bytes(content)
        written.append(dest_file)
    return written


@app.command("add")
def add(
    name: str = typer.Argument(..., help="Stack pack name, e.g. python or react"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    written = apply_pack(workspace, name)

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

    console.print(f"stack '{name}': {len(written)} file(s) written to .claude/standards/{name}/")

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
