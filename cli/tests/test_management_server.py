"""Tests for Phase 3.1.1: ingest delegation via the KG server's HTTP routes.

Covers:
  - GET  /health          on the KG server's Starlette app
  - POST /api/ingest      success path and unknown-workspace 422
  - `cartographer seed`   delegates when serve is reachable, falls back to the
                          direct ingestion path when it is not

The KG server's HTTP app is built directly via `_build_http_app()` and driven
with starlette.testclient — no uvicorn process or watcher thread is started,
so these tests are fast and hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient
from typer.testing import CliRunner

from cartographer import registry
from cartographer.cli import app as cli_app
from cartographer.ingestion.embedder import Embedder, EMBEDDING_DIM
from cartographer.runtime.mcp_servers import kg_server

runner = CliRunner()


class StubEmbedder(Embedder):
    """Deterministic fixed-length vectors, no model download."""

    def __init__(self):
        self._model_name = "stub"
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] + [0.0] * (EMBEDDING_DIM - 1) for t in texts]

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM


def _init_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    result = runner.invoke(cli_app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_reports_ok_and_watch_flag():
    app = kg_server._build_http_app(watch=True)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["watch"] is True
    assert isinstance(body["pid"], int)


def test_health_reports_watch_disabled_by_default():
    app = kg_server._build_http_app(watch=False)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.json()["watch"] is False


# ---------------------------------------------------------------------------
# POST /api/ingest
# ---------------------------------------------------------------------------

def test_ingest_endpoint_processes_files(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setattr("cartographer.ingestion.embedder.get_embedder", lambda: StubEmbedder())

    doc = tmp_path / "note.md"
    doc.write_text("# Hello\n\nSome content for the knowledge base.", encoding="utf-8")

    app = kg_server._build_http_app(watch=False)
    client = TestClient(app)
    resp = client.post("/api/ingest", json={
        "workspace": str(tmp_path),
        "paths": [str(doc)],
        "scope": "local",
    })

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["files_processed"] == 1
    assert body["chunks_upserted"] >= 1
    assert body["errors"] == []


def test_ingest_endpoint_unknown_workspace_returns_422(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    app = kg_server._build_http_app(watch=False)
    client = TestClient(app)
    resp = client.post("/api/ingest", json={
        "workspace": str(tmp_path / "does-not-exist"),
        "paths": ["/tmp/whatever.md"],
        "scope": "local",
    })
    assert resp.status_code == 422


def test_ingest_endpoint_missing_fields_returns_422(tmp_path):
    app = kg_server._build_http_app(watch=False)
    client = TestClient(app)
    resp = client.post("/api/ingest", json={"workspace": str(tmp_path)})
    assert resp.status_code == 422


def test_ingest_endpoint_unregistered_project_returns_422(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    # cartographer.toml exists but the project was never registered
    (tmp_path / "cartographer.toml").write_text(
        '[project]\nid = "proj_orphan"\nname = "orphan"\n', encoding="utf-8"
    )
    app = kg_server._build_http_app(watch=False)
    client = TestClient(app)
    resp = client.post("/api/ingest", json={
        "workspace": str(tmp_path),
        "paths": ["/tmp/whatever.md"],
        "scope": "local",
    })
    assert resp.status_code == 422
    assert "not registered" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# `cartographer seed` delegation vs. direct fallback
# ---------------------------------------------------------------------------

def test_seed_delegates_when_serve_reachable(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    doc = tmp_path / "note.md"
    doc.write_text("content", encoding="utf-8")

    from cartographer.commands import seed as seed_cmd

    monkeypatch.setattr(seed_cmd, "_serve_reachable", lambda port: True)
    monkeypatch.setattr(
        seed_cmd,
        "_delegate_to_serve",
        lambda port, workspace, paths, enrich: {
            "files_processed": 1,
            "files_skipped": 0,
            "chunks_upserted": 3,
            "nodes_upserted": 1,
            "edges_upserted": 0,
            "errors": [],
        },
    )

    result = runner.invoke(cli_app, ["seed", str(doc), "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "delegating to cartographer serve" in result.output
    assert "processed: 1" in result.output
    assert "chunks: 3" in result.output


def test_seed_falls_back_to_direct_path_when_serve_not_reachable(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    monkeypatch.setattr("cartographer.ingestion.embedder.get_embedder", lambda: StubEmbedder())

    doc = tmp_path / "note.md"
    doc.write_text("content for direct ingestion", encoding="utf-8")

    from cartographer.commands import seed as seed_cmd
    monkeypatch.setattr(seed_cmd, "_serve_reachable", lambda port: False)

    result = runner.invoke(cli_app, ["seed", str(doc), "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "delegating to cartographer serve" not in result.output
    assert "processed: 1" in result.output


def test_seed_reports_delegation_errors_and_exits_nonzero(tmp_path, monkeypatch):
    _init_project(tmp_path, monkeypatch)
    doc = tmp_path / "note.md"
    doc.write_text("content", encoding="utf-8")

    from cartographer.commands import seed as seed_cmd

    monkeypatch.setattr(seed_cmd, "_serve_reachable", lambda port: True)
    monkeypatch.setattr(
        seed_cmd,
        "_delegate_to_serve",
        lambda port, workspace, paths, enrich: (_ for _ in ()).throw(RuntimeError("serve rejected ingest request (422): boom")),
    )

    result = runner.invoke(cli_app, ["seed", str(doc), "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_serve_reachable_false_when_nothing_listening():
    from cartographer.commands.seed import _serve_reachable
    # Port unlikely to have a listener during tests.
    assert _serve_reachable(59999) is False
