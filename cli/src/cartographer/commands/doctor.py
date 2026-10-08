"""`cartographer doctor`: validate config, local index reachability, and MCP wiring."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from cartographer import config as config_mod, taxonomy as taxonomy_mod
from cartographer.indexing import kg, vdb
from cartographer.ingestion import parsers as parser_registry
from cartographer.runtime import serve_state

console = Console()


def run(
    path: Path = typer.Option(Path("."), "--path", help="Workspace root"),
) -> None:
    workspace = path.resolve()
    healthy = True

    if not config_mod.config_exists(workspace):
        console.print("[red]FAIL[/red] cartographer.toml not found; run 'cartographer init'")
        raise typer.Exit(code=1)

    try:
        cfg = config_mod.load_config(workspace)
        console.print("[green]OK[/green]   cartographer.toml parses and validates")
    except Exception as exc:  # noqa: BLE001 - this is the CLI's user-facing report boundary
        console.print(f"[red]FAIL[/red] cartographer.toml invalid: {exc}")
        raise typer.Exit(code=1) from exc

    local_dir = workspace / ".cartographer" / "local"
    indexing_enabled = cfg.topology.mode != "none"

    serve = serve_state.current_running_state() if indexing_enabled else None

    if not indexing_enabled:
        console.print("[yellow]INFO[/yellow] indexing disabled (topology=none) -- skipping local KG/VDB checks")
    else:
        if vdb.is_readable(local_dir / "vdb.lance"):
            console.print("[green]OK[/green]   local VDB opens")
        else:
            console.print("[red]FAIL[/red] local VDB not readable")
            healthy = False

        if kg.is_readable(local_dir / "kg.kuzu"):
            console.print("[green]OK[/green]   local KG opens")
        elif serve is not None:
            # Kuzu's single-writer-per-file lock (see kg.py's _connect docstring)
            # means a read-only open from this process can never succeed while
            # `cartographer serve` holds the write handle -- expected and healthy,
            # not a failure. Without this check, doctor would always report FAIL
            # for the KG on every actively-served project, which is the common
            # case, not an edge case.
            console.print("[green]OK[/green]   local KG is managed by the running 'cartographer serve' (write-locked, as expected)")
        else:
            console.print("[red]FAIL[/red] local KG not readable")
            healthy = False

    if cfg.topology.mode == "central":
        override = config_mod.load_local_override(workspace)
        if not override.promotion_token:
            console.print("[yellow]INFO[/yellow] central: promotion_token not set in .cartographer.local.toml")
        else:
            console.print("[green]OK[/green]   central: promotion_token present")

        try:
            from cartographer.indexing.central import get_central_vdb
            vdb_driver_name = cfg.central.vdb_driver
            central_vdb = get_central_vdb(cfg, override)
            if central_vdb.is_reachable():
                console.print(f"[green]OK[/green]   central VDB ({vdb_driver_name}) is reachable")
            else:
                console.print(f"[red]FAIL[/red] central VDB ({vdb_driver_name}) is not reachable; check [central_vdb]/[central_vdb_s3] in .cartographer.local.toml")
                healthy = False
        except (ValueError, NotImplementedError) as exc:
            console.print(f"[yellow]INFO[/yellow] central VDB: {exc}")
        except ImportError:
            console.print("[yellow]INFO[/yellow] central VDB: psycopg2 not installed; run: pip install 'cartographer[central]'")

        try:
            from cartographer.indexing.central import get_central_kg
            central_kg = get_central_kg(cfg, override)
            if central_kg.is_reachable():
                console.print("[green]OK[/green]   central KG (Neo4j) is reachable")
            else:
                console.print("[red]FAIL[/red] central KG (Neo4j) is not reachable; check [central_kg] in .cartographer.local.toml")
                healthy = False
        except (ValueError, NotImplementedError) as exc:
            console.print(f"[yellow]INFO[/yellow] central KG: {exc}")
        except ImportError:
            console.print("[yellow]INFO[/yellow] central KG: neo4j not installed; run: pip install 'cartographer[central]'")

    if indexing_enabled:
        if serve is not None:
            kg_health = serve_state.check_health(serve.kg_port)
            watching = bool((kg_health or {}).get("watch"))
            console.print(
                f"[green]OK[/green]   cartographer serve is running (pid {serve.pid}, "
                f"{'watching' if watching else 'not watching'})"
            )
        else:
            console.print(
                "[yellow]INFO[/yellow] cartographer serve is not running — "
                "local index will not auto-update on file changes"
            )

        mcp_path = workspace / ".mcp.json"
        mcp_wired = False
        if mcp_path.exists():
            try:
                data = json.loads(mcp_path.read_text(encoding="utf-8"))
                mcp_wired = any(k.startswith("cartographer") for k in data.get("mcpServers", {}))
            except json.JSONDecodeError:
                pass

        if mcp_wired:
            console.print("[green]OK[/green]   Cartographer MCP entries present in .mcp.json")
        else:
            console.print("[yellow]INFO[/yellow] Cartographer MCP entries not found; run 'cartographer init'")

    if cfg.taxonomy.version == taxonomy_mod.CANONICAL_TAXONOMY_VERSION:
        console.print(f"[green]OK[/green]   edge taxonomy pinned version ({cfg.taxonomy.version}) matches installed CLI")
    else:
        console.print(
            f"[yellow]INFO[/yellow] edge taxonomy version drift: project pins {cfg.taxonomy.version!r}, "
            f"installed CLI is {taxonomy_mod.CANONICAL_TAXONOMY_VERSION!r} — see 'cartographer taxonomy list'"
        )

    if indexing_enabled and kg.is_readable(local_dir / "kg.kuzu"):
        try:
            rows = kg.query(local_dir / "kg.kuzu", "MATCH ()-[r:RelatesTo]->() RETURN DISTINCT r.type AS type")
            drift = taxonomy_mod.lint_edge_types({r["type"] for r in rows if r.get("type")})
            if drift:
                console.print(
                    f"[yellow]INFO[/yellow] local KG uses edge type(s) outside the canonical taxonomy: {', '.join(sorted(drift))}"
                )
        except Exception:
            pass  # best-effort drift check; doctor's core health checks already covered KG readability above

    for stack_name in cfg.stacks.active:
        hint = parser_registry.STACK_PARSER_HINTS.get(stack_name)
        if hint is None:
            continue
        import_name, extra, filetypes, packages = hint
        if parser_registry.is_parser_installed(import_name):
            console.print(f"[green]OK[/green]   '{stack_name}' stack: real {filetypes} parser installed")
        else:
            cmd = parser_registry.install_hint(extra, packages)
            console.print(
                f"[yellow]INFO[/yellow] '{stack_name}' stack: {filetypes} files use a regex fallback "
                f"(no calls/extends edges); run: {cmd}"
            )

    if not healthy:
        raise typer.Exit(code=1)
    console.print("[bold green]doctor: all local checks passed[/bold green]")
