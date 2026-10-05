"""`cartographer recall <query>`: query the registry then the local index.

This is a debugging aid; the real path for cross-project recall is the bundled
recall skill (PROJECT_BRIEF.md Section 6.3), installed by 'cartographer init'. This command still enforces the same isolation rule the skill will: a query
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
        console.print(f"  - [{hit['type']}] {hit['path']}", markup=False)

    if cfg.topology.mode == "central":
        try:
            from cartographer.indexing.central import get_central_kg, get_central_vdb
            override = config_mod.load_local_override(workspace)
            central_kg = get_central_kg(cfg, override)
            if central_kg.is_reachable():
                central_kg_hits = central_kg.query(
                    "MATCH (a:Artifact) WHERE a.path CONTAINS $q OR a.attrs CONTAINS $q "
                    "RETURN a.id AS id, a.type AS type, a.path AS path, a.tombstoned_at AS tombstoned_at LIMIT 20",
                    {"q": query},
                )
                console.print(f"KG matches (origin=global): {len(central_kg_hits)}")
                for hit in central_kg_hits[:10]:
                    if hit.get("tombstoned_at"):
                        redirect = central_kg.find_supersedes_source(hit["path"])
                        if redirect:
                            central_vdb = get_central_vdb(cfg, override)
                            new_content = central_vdb.query_by_path(cfg.project.id, redirect["new_path"])
                            if new_content:
                                console.print(
                                    f"  - [{hit['type']}|renamed] {hit['path']} -> {redirect['new_path']}",
                                    markup=False,
                                )
                        # tombstoned with no supersedes edge is a pure deletion — excluded
                        continue
                    console.print(f"  - [{hit['type']}] {hit['path']}", markup=False)
            else:
                console.print("[yellow]central KG unreachable — showing local KG results only[/yellow]")
        except Exception:
            console.print("[yellow]central KG unavailable — showing local KG results only[/yellow]")

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
    local_hits = vdb.query(local_dir / "vdb.lance", scope="local", embedding=embedding, k=k)

    global_hits: list[dict] = []
    central_vdb_handle = None
    if cfg.topology.mode == "central":
        try:
            from cartographer.indexing.central import get_central_vdb
            override = config_mod.load_local_override(workspace)
            central_vdb = get_central_vdb(cfg, override)
            if central_vdb.is_reachable():
                central_vdb_handle = central_vdb
                global_hits = central_vdb.query(cfg.project.id, embedding=embedding, k=k, where="is_tombstone = FALSE")
                for h in global_hits:
                    h["origin"] = "global"
            else:
                console.print("[yellow]central index unreachable — showing local results only[/yellow]")
        except Exception:
            console.print("[yellow]central index unavailable — showing local results only[/yellow]")

    if cfg.retrieval.conflict_notice:
        from cartographer.conflict import detect_conflicts
        for notice in detect_conflicts(local_hits, central_vdb_handle, cfg.project.id, cfg.retrieval.conflict_threshold_seconds):
            console.print(f"[yellow]{notice}[/yellow]")

    local_paths = {h.get("path") for h in local_hits}
    merged = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]

    console.print(f"VDB matches: {len(merged)}")
    for hit in merged:
        origin = hit.get("origin", "local")
        artifact_type = hit.get("artifact_type", "code")
        console.print(f"  - [{artifact_type}|{origin}] {hit['path']} :: {hit['text'][:80]}", markup=False)
