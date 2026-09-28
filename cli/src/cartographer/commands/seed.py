"""`cartographer seed <path>`: ingest a documentation or code source into the local index.

Accepts a file, a directory, or a glob pattern. Skips binary formats with a warning
(they require a Claude Code session for extraction). Reports a summary on completion.

Idempotent: the underlying VDB and KG upserts are keyed on artifact identity.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod, registry
from cartographer.ingestion import pipeline as ingest_pipeline
from cartographer.ingestion import text_extractor

console = Console()


def run(
    source: Path = typer.Argument(..., help="File or directory to ingest"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root (where cartographer.toml lives)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recurse into subdirectories"),
    enrich: bool = typer.Option(False, "--enrich/--no-enrich", help="Use Claude to extract semantic KG relationships (slower, requires claude CLI)."),
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

    if source.is_file():
        paths = [source]
    else:
        paths = text_extractor.collect_paths(source, recursive=recursive)

    if not paths:
        console.print("[yellow]no ingestable files found[/yellow]")
        return

    console.print(f"  {len(paths)} file(s) found")

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
        )

    console.print(f"  processed: {result.files_processed}")
    if result.files_skipped:
        console.print(f"  [yellow]skipped: {result.files_skipped}[/yellow]")
        for msg in result.skipped_paths[:5]:
            console.print(f"    - {msg}")
        if len(result.skipped_paths) > 5:
            console.print(f"    ... and {len(result.skipped_paths) - 5} more")

    if result.errors:
        console.print(f"  [red]errors: {len(result.errors)}[/red]")
        for msg in result.errors[:5]:
            console.print(f"    - {msg}")

    console.print(f"  chunks: {result.chunks_upserted}  nodes: {result.nodes_upserted}  edges: {result.edges_upserted}")

    if result.errors:
        raise typer.Exit(code=1)

    console.print("[bold green]seed complete[/bold green]")
