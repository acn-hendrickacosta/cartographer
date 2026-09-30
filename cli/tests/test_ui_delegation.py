"""Tests for Phase 3.1.2: cartographer ui's KG read delegation.

`ui/server.py`'s /api/graph, /api/files, /api/stats routes check whether the
KG server (port 4011) is reachable and delegate to its /api/query and
/api/neighbors routes when it is, falling back to opening kg.kuzu directly
otherwise. These tests exercise both paths by monkeypatching
`cartographer.ui.server._serve_reachable` and `_post` — no real HTTP server is
started for either side.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cartographer import registry
from cartographer.cli import app as cli_app
from cartographer.ingestion.embedder import Embedder, EMBEDDING_DIM
from cartographer.ui import server as ui_server

runner = CliRunner()


class StubEmbedder(Embedder):
    def __init__(self):
        self._model_name = "stub"
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] + [0.0] * (EMBEDDING_DIM - 1) for t in texts]

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM


def _init_and_seed(tmp_path: Path, monkeypatch) -> str:
    """Init a project and ingest one file directly (no serve). Returns the
    ingested artifact's node id."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    result = runner.invoke(cli_app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    monkeypatch.setattr("cartographer.ingestion.embedder.get_embedder", lambda: StubEmbedder())
    doc = tmp_path / "note.md"
    doc.write_text("# Hello\n\nSome content.", encoding="utf-8")

    # Force the direct ingestion path regardless of whether a real
    # `cartographer serve` happens to be running on this machine (port 4011) —
    # these tests seed a throwaway tmp_path project that a real serve process
    # would correctly reject as unregistered.
    from cartographer.commands import seed as seed_cmd
    monkeypatch.setattr(seed_cmd, "_serve_reachable", lambda port: False)

    seed_result = runner.invoke(cli_app, ["seed", str(doc), "--path", str(tmp_path)])
    assert seed_result.exit_code == 0, seed_result.output

    from cartographer.indexing import kg as kg_driver
    rows = kg_driver.query(
        tmp_path / ".cartographer" / "local" / "kg.kuzu",
        "MATCH (a:Artifact) RETURN a.id AS id LIMIT 1",
    )
    assert rows
    return rows[0]["id"]


def test_files_uses_direct_path_when_serve_not_reachable(tmp_path, monkeypatch):
    _init_and_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_server, "_serve_reachable", lambda port: False)

    app = ui_server.build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/files")

    assert resp.status_code == 200
    assert any(f["path"] == "note.md" for f in resp.json()["files"])


def test_files_delegates_when_serve_reachable(tmp_path, monkeypatch):
    node_id = _init_and_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_server, "_serve_reachable", lambda port: True)

    captured = {}

    def fake_post(port, route, payload):
        captured["route"] = route
        captured["payload"] = payload
        return {"results": [{"id": node_id, "path": "note.md", "type": "doc"}]}

    monkeypatch.setattr(ui_server, "_post", fake_post)

    app = ui_server.build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/files")

    assert resp.status_code == 200
    assert resp.json()["files"] == [{"id": node_id, "path": "note.md", "type": "doc"}]
    assert captured["route"] == "/api/query"
    assert captured["payload"]["workspace"] == str(tmp_path)


def test_files_falls_back_to_direct_when_delegation_raises(tmp_path, monkeypatch):
    _init_and_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_server, "_serve_reachable", lambda port: True)

    def failing_post(port, route, payload):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(ui_server, "_post", failing_post)

    app = ui_server.build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/files")

    # Delegation raised, but the direct fallback path still succeeds.
    assert resp.status_code == 200
    assert any(f["path"] == "note.md" for f in resp.json()["files"])


def test_graph_delegates_neighbors_and_query(tmp_path, monkeypatch):
    node_id = _init_and_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_server, "_serve_reachable", lambda port: True)

    calls = []

    def fake_post(port, route, payload):
        calls.append(route)
        if route == "/api/neighbors":
            return {"neighbors": []}
        return {"results": [{"id": node_id, "type": "doc", "path": "note.md", "scope": "local"}]}

    monkeypatch.setattr(ui_server, "_post", fake_post)

    app = ui_server.build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/graph", params={"node_id": node_id})

    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == [{"id": node_id, "type": "doc", "path": "note.md", "scope": "local"}]
    assert "/api/neighbors" in calls
    assert "/api/query" in calls


def test_stats_soft_degrades_on_lock_error_without_serve(tmp_path, monkeypatch):
    _init_and_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(ui_server, "_serve_reachable", lambda port: False)

    from cartographer.indexing import kg as kg_driver

    def raise_lock(*args, **kwargs):
        raise RuntimeError("IO exception: Could not set lock on file")

    monkeypatch.setattr(kg_driver, "query", raise_lock)

    app = ui_server.build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/stats")

    assert resp.status_code == 200
    assert resp.json()["kg"]["_error"] == "locked"
