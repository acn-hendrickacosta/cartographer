"""FastAPI application for `cartographer ui`.

JSON API routes back the single-page HTML UI:
  GET /api/search?q=<text>&k=<int>     — VDB semantic search
  GET /api/graph?node_id=<id>&depth=<n> — KG neighbors
  GET /api/files                        — whole-file nodes, for the tree browser
  GET /api/registry                     — all registered projects
  GET /api/stats                        — VDB and KG counts

KG routes delegate to the KG server (port 4011) when `cartographer serve` is
running, instead of opening kg.kuzu directly. Once that server's watcher has
done one write, it holds Kuzu's exclusive write lock for its entire lifetime
(see kg.py's _rw_db_cache), so a second process trying to open the KG
read-only would otherwise be permanently blocked, not just during a brief
flush window. Delegated queries run inside the KG server process and reuse
its already-open handle, so they never hit that lock. See
docs/phases/phase-3.1.2-ui-read-delegation.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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

KG_SERVER_PORT = 4011
_HEALTH_TIMEOUT = 0.5
_QUERY_TIMEOUT = 30


def _serve_reachable(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=_HEALTH_TIMEOUT)
        return True
    except Exception:
        return False


def _post(port: int, route: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{route}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_QUERY_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"kg server rejected request ({exc.code}): {detail}") from exc


def build_app(workspace: Path) -> FastAPI:
    app = FastAPI(title="Cartographer UI", docs_url=None, redoc_url=None)

    cfg = config_mod.load_config(workspace)
    project_id = cfg.project.id
    local_dir = workspace / ".cartographer" / "local"
    vdb_path = local_dir / "vdb.lance"
    kg_path = local_dir / "kg.kuzu"

    def _kg_query(cypher: str, params: dict | None = None) -> list[dict]:
        if _serve_reachable(KG_SERVER_PORT):
            try:
                result = _post(KG_SERVER_PORT, "/api/query", {
                    "workspace": str(workspace), "cypher": cypher, "params": params,
                })
                return result["results"]
            except Exception:
                pass  # serve looked reachable but the delegated call failed; fall through
        try:
            return kg_driver.query(kg_path, cypher, params)
        except RuntimeError as exc:
            if "lock" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Knowledge graph is temporarily locked by an indexing process. Retry in a moment.",
                )
            raise

    def _kg_neighbors(node_id: str, depth: int, scope: str) -> list[dict]:
        if _serve_reachable(KG_SERVER_PORT):
            try:
                result = _post(KG_SERVER_PORT, "/api/neighbors", {
                    "workspace": str(workspace), "node_id": node_id, "depth": depth, "scope": scope,
                })
                return result["neighbors"]
            except Exception:
                pass
        try:
            return kg_driver.neighbors(kg_path, node_id=node_id, depth=depth, scope=scope)
        except RuntimeError as exc:
            if "lock" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Knowledge graph is temporarily locked by an indexing process. Retry in a moment.",
                )
            raise

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
        nodes = _kg_neighbors(node_id, depth, "local")

        # Also include the requested node itself
        root_rows = _kg_query(
            "MATCH (a:Artifact {id: $id}) RETURN a.id AS id, a.type AS type, a.path AS path, a.scope AS scope",
            {"id": node_id},
        )
        all_nodes = root_rows + nodes

        # Fetch edges between visible nodes
        visible_ids = {n["id"] for n in all_nodes}
        id_list = "', '".join(visible_ids)
        edges = _kg_query(
            f"MATCH (a:Artifact)-[r:RelatesTo]->(b:Artifact) "
            f"WHERE a.id IN ['{id_list}'] AND b.id IN ['{id_list}'] "
            "RETURN a.id AS src, b.id AS dst, r.type AS type",
        )
        return JSONResponse({"nodes": all_nodes, "edges": edges})

    @app.get("/api/files")
    def files():
        rows = _kg_query(
            "MATCH (a:Artifact) WHERE a.type IN ['module', 'doc', 'spec'] "
            "RETURN a.id AS id, a.path AS path, a.type AS type ORDER BY a.path",
        )
        return JSONResponse({"files": rows})

    @app.get("/api/project")
    def project_info():
        return JSONResponse({
            "id": project_id,
            "name": cfg.project.name,
            "topology": cfg.topology.mode,
            "workspace": str(workspace),
        })

    @app.get("/api/registry")
    def registry_view():
        projects = registry.list_projects()
        return JSONResponse({"projects": [p.__dict__ for p in projects]})

    @app.get("/api/stats")
    def stats():
        vdb_counts: dict = {}
        kg_counts: dict = {}

        if vdb_path.exists():
            rows = vdb_driver.scan(vdb_path, scope="local", columns=["artifact_type"])
            for r in rows:
                atype = r.get("artifact_type", "unknown")
                vdb_counts[atype] = vdb_counts.get(atype, 0) + 1

        if kg_path.exists():
            try:
                node_rows = _kg_query("MATCH (a:Artifact) RETURN a.type AS type, count(*) AS cnt")
                for r in node_rows:
                    kg_counts[r["type"]] = r.get("cnt", 0)
            except HTTPException as exc:
                if exc.status_code == 503:
                    kg_counts["_error"] = "locked"
                else:
                    raise

        return JSONResponse({"vdb": vdb_counts, "kg": kg_counts})

    # Serve the single-page UI
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app
