"""`cartographer seed <path>`: ingest a documentation or code source into the local index.

Accepts a file, a directory, or a glob pattern. Skips binary formats with a warning
(they require a Claude Code session for extraction). Reports a summary on completion.

Idempotent: the underlying VDB and KG upserts are keyed on artifact identity.

When `cartographer serve` is running, delegates ingestion to its KG server
(POST /api/ingest, default port 4011) instead of opening the local KG directly.
That subprocess already holds the KG's write lock via the background watcher
(Phase 3.1.1); a second writer from this process would collide with it under
Kuzu's exclusive-lock model. See docs/phases/phase-3.1.1-management-server.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod, registry
from cartographer.ingestion import pipeline as ingest_pipeline
from cartographer.ingestion import text_extractor

console = Console()

KG_SERVER_PORT = 4011
_HEALTH_TIMEOUT = 0.5
_INGEST_TIMEOUT = 600


def _serve_reachable(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=_HEALTH_TIMEOUT)
        return True
    except Exception:
        return False


def _delegate_to_serve(port: int, workspace: Path, paths: list[Path], enrich: bool, strict: bool) -> dict:
    payload = json.dumps({
        "workspace": str(workspace),
        "paths": [str(p) for p in paths],
        "scope": "local",
        "enrich": enrich,
        "strict": strict,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/ingest",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_INGEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"serve rejected ingest request ({exc.code}): {detail}") from exc


def run(
    source: Path = typer.Argument(..., help="File or directory to ingest"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root (where cartographer.toml lives)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recurse into subdirectories"),
    enrich: bool = typer.Option(False, "--enrich/--no-enrich", help="Use Claude to extract semantic KG relationships (slower, requires claude CLI)."),
    strict: bool = typer.Option(False, "--strict", help="Fail a file instead of warning when it emits an edge type outside the canonical taxonomy (cartographer taxonomy list)."),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    cfg = config_mod.load_config(workspace)
    record = registry.get_project(cfg.project.id)
    if record is None:
        console.print("[red]project not registered; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    source = source.resolve()
    if not source.exists():
        console.print(f"[red]path does not exist: {source}[/red]")
        raise typer.Exit(code=1)

    local_dir = workspace / ".cartographer" / "local"
    vdb_path = local_dir / "vdb.lance"
    kg_path = local_dir / "kg.kuzu"

    console.print(f"[bold]cartographer seed[/bold] {source}")

    if source.is_file():
        paths = [source]
    else:
        paths = text_extractor.collect_paths(source, recursive=recursive)

    if not paths:
        console.print("[yellow]no ingestable files found[/yellow]")
        return

    console.print(f"  {len(paths)} file(s) found")

    if _serve_reachable(KG_SERVER_PORT):
        console.print(f"  [cyan]delegating to cartographer serve (port {KG_SERVER_PORT})…[/cyan]")
        try:
            result = _delegate_to_serve(KG_SERVER_PORT, workspace, paths, enrich, strict)
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)

        console.print(f"  processed: {result['files_processed']}")
        if result.get("files_skipped"):
            console.print(f"  [yellow]skipped: {result['files_skipped']}[/yellow]")
        if result.get("taxonomy_warnings"):
            console.print(f"  [yellow]taxonomy warnings: {len(result['taxonomy_warnings'])}[/yellow]")
            for msg in result["taxonomy_warnings"][:5]:
                console.print(f"    - {msg}")
        if result.get("errors"):
            console.print(f"  [red]errors: {len(result['errors'])}[/red]")
            for msg in result["errors"][:5]:
                console.print(f"    - {msg}")
        console.print(
            f"  chunks: {result['chunks_upserted']}  "
            f"nodes: {result['nodes_upserted']}  edges: {result['edges_upserted']}"
        )

        if result.get("errors"):
            raise typer.Exit(code=1)

        console.print("[bold green]seed complete[/bold green]")
        return

    if enrich:
        from cartographer.ingestion.kg_enricher import is_available as claude_available
        if not claude_available():
            console.print("[red]--enrich requires the `claude` CLI on PATH; not found[/red]")
            raise typer.Exit(code=1)
        console.print("[yellow]--enrich enabled: Claude will analyse each file for semantic relationships.[/yellow]")
        console.print("[yellow]Expect ~30-60s per file. Run on a subset first if testing.[/yellow]")

    try:
        from cartographer.ingestion.embedder import get_embedder
        embedder = get_embedder()
    except ImportError as exc:
        console.print(f"[red]embedder not available: {exc}[/red]")
        raise typer.Exit(code=1)

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("embedding", total=len(paths))
        result = ingest_pipeline.ingest_paths(
            paths,
            project_id=cfg.project.id,
            workspace_root=workspace,
            vdb_path=vdb_path,
            kg_path=kg_path,
            scope="local",
            embedder=embedder,
            on_file=lambda _p: progress.advance(task),
            enrich=enrich,
            strict=strict,
        )

    console.print(f"  processed: {result.files_processed}")
    if result.files_skipped:
        console.print(f"  [yellow]skipped: {result.files_skipped}[/yellow]")
        for msg in result.skipped_paths[:5]:
            console.print(f"    - {msg}")
        if len(result.skipped_paths) > 5:
            console.print(f"    ... and {len(result.skipped_paths) - 5} more")

    if result.taxonomy_warnings:
        console.print(f"  [yellow]taxonomy warnings: {len(result.taxonomy_warnings)}[/yellow]")
        for msg in result.taxonomy_warnings[:5]:
            console.print(f"    - {msg}")

    if result.errors:
        console.print(f"  [red]errors: {len(result.errors)}[/red]")
        for msg in result.errors[:5]:
            console.print(f"    - {msg}")

    console.print(f"  chunks: {result.chunks_upserted}  nodes: {result.nodes_upserted}  edges: {result.edges_upserted}")

    if result.errors:
        raise typer.Exit(code=1)

    console.print("[bold green]seed complete[/bold green]")
