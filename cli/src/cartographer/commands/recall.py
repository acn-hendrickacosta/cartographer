"""`cartographer recall <query>`: query the registry then the local index.

This is a debugging aid; the real path for cross-project recall is the plugin's
recall skill (PROJECT_BRIEF.md Section 6.3), which is not built in this CLI-only
slice. This command still enforces the same isolation rule the skill will: a query
never returns results for a project outside the caller's tenant.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod, registry
from cartographer.indexing import kg, vdb

console = Console()


def run(
    query: str = typer.Argument(..., help="What to recall"),
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
    k: int = typer.Option(8, "--k", help="Max VDB results"),
) -> None:
    workspace = path.resolve()
    if not config_mod.config_exists(workspace):
        console.print("[red]no cartographer.toml found; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)

    cfg = config_mod.load_config(workspace)
    record = registry.get_project(cfg.project.id)
    if record is None:
        console.print("[red]project not found in registry; run 'cartographer init' first[/red]")
        raise typer.Exit(code=1)
    if record.tenant != cfg.isolation.tenant:
        # Isolation is a hard boundary (Section 9): never return results across a
        # tenant mismatch, even locally.
        console.print("[red]tenant mismatch between registry and local config; refusing to query[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]recall[/bold] '{query}' -- project={record.project_id} tenant={record.tenant}")

    local_dir = workspace / ".cartographer" / "local"
    kg_hits = kg.query(
        local_dir / "kg.kuzu",
        "MATCH (a:Artifact) WHERE a.path CONTAINS $q OR a.attrs CONTAINS $q "
        "RETURN a.id AS id, a.type AS type, a.path AS path LIMIT 20",
        {"q": query},
    )
    console.print(f"KG matches (origin=local): {len(kg_hits)}")
    for hit in kg_hits[:10]:
        console.print(f"  - [{hit['type']}] {hit['path']}")

    try:
        from fastembed import TextEmbedding
    except ImportError:
        console.print(
            "[yellow]semantic recall skipped[/yellow]: install with "
            "'pip install \"cartographer[embeddings]\"' to enable VDB queries"
        )
        return

    embedder = TextEmbedding()
    embedding = list(next(embedder.embed([query])))
    vdb_hits = vdb.query(local_dir / "vdb.lance", scope="local", embedding=embedding, k=k)
    console.print(f"VDB matches (origin=local): {len(vdb_hits)}")
    for hit in vdb_hits:
        console.print(f"  - {hit['path']} :: {hit['text'][:80]}")
