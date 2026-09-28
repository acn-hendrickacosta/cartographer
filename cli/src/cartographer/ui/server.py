"""FastAPI application for `cartographer ui`.

Four JSON API routes back the single-page HTML UI:
  GET /api/search?q=<text>&k=<int>     — VDB semantic search
  GET /api/graph?node_id=<id>&depth=<n> — KG neighbors
  GET /api/registry                     — all registered projects
  GET /api/stats                        — VDB and KG counts
"""

from __future__ import annotations

from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as _err:
    raise ImportError(
        "FastAPI is required for `cartographer ui`. "
        "Install it with: pip install \"cartographer-cli[ui]\""
    ) from _err

from cartographer import config as config_mod, registry
from cartographer.indexing import kg as kg_driver
from cartographer.indexing import vdb as vdb_driver

STATIC_DIR = Path(__file__).parent / "static"


def build_app(workspace: Path) -> FastAPI:
    app = FastAPI(title="Cartographer UI", docs_url=None, redoc_url=None)

    cfg = config_mod.load_config(workspace)
    project_id = cfg.project.id
    local_dir = workspace / ".cartographer" / "local"
    vdb_path = local_dir / "vdb.lance"
    kg_path = local_dir / "kg.kuzu"

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1), k: int = Query(8, ge=1, le=50)):
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise HTTPException(status_code=503, detail="fastembed not installed")

        embedder = TextEmbedding()
        embedding = list(next(embedder.embed([q])))
        hits = vdb_driver.query(vdb_path, scope="local", embedding=embedding, k=k)
        return JSONResponse({"results": hits})

    @app.get("/api/graph")
    def graph(node_id: str = Query(...), depth: int = Query(1, ge=1, le=4)):
        nodes = kg_driver.neighbors(kg_path, node_id=node_id, depth=depth, scope="local")

        # Also include the requested node itself
        root_rows = kg_driver.query(
            kg_path,
            "MATCH (a:Artifact {id: $id}) RETURN a.id AS id, a.type AS type, a.path AS path, a.scope AS scope",
            {"id": node_id},
        )
        all_nodes = root_rows + nodes

        # Fetch edges between visible nodes
        visible_ids = {n["id"] for n in all_nodes}
        id_list = "', '".join(visible_ids)
        edges = kg_driver.query(
            kg_path,
            f"MATCH (a:Artifact)-[r:RelatesTo]->(b:Artifact) "
            f"WHERE a.id IN ['{id_list}'] AND b.id IN ['{id_list}'] "
            "RETURN a.id AS src, b.id AS dst, r.type AS type",
        )
        return JSONResponse({"nodes": all_nodes, "edges": edges})

    @app.get("/api/registry")
    def registry_view():
        projects = registry.list_projects()
        return JSONResponse({"projects": [p.__dict__ for p in projects]})

    @app.get("/api/stats")
    def stats():
        vdb_counts: dict = {}
        kg_counts: dict = {}

        if vdb_path.exists():
            rows = vdb_driver.query(
                vdb_path, scope="local",
                embedding=[0.0] * vdb_driver.DEFAULT_EMBEDDING_DIM,
                k=0,
                where="id IS NOT NULL",
            )
            for r in rows:
                atype = r.get("artifact_type", "unknown")
                vdb_counts[atype] = vdb_counts.get(atype, 0) + 1

        if kg_path.exists():
            node_rows = kg_driver.query(
                kg_path,
                "MATCH (a:Artifact) RETURN a.type AS type, count(*) AS cnt",
            )
            for r in node_rows:
                kg_counts[r["type"]] = r.get("cnt", 0)

        return JSONResponse({"vdb": vdb_counts, "kg": kg_counts})

    # Serve the single-page UI
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app
