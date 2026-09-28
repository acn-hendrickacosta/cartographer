"""Integration tests for the ingestion pipeline.

These tests use real LanceDB and Kuzu instances via tmp_path.
They do NOT use fastembed (to avoid the model download in CI);
instead they inject a stub embedder that returns deterministic vectors.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from cartographer.ingestion import pipeline as ingest_pipeline
from cartographer.ingestion.embedder import Embedder, EMBEDDING_DIM


class StubEmbedder(Embedder):
    """Returns deterministic fixed-length vectors without loading a model."""

    def __init__(self):
        self._model_name = "stub"
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Each text gets a vector whose first element is its length, rest zeros
        return [[float(len(t))] + [0.0] * (EMBEDDING_DIM - 1) for t in texts]

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM


def test_ingest_single_markdown_file(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    docs = workspace / "docs"
    docs.mkdir()
    (docs / "overview.md").write_text("# Overview\nThis is the project overview.\n")

    vdb_path = tmp_path / "vdb.lance"
    kg_path = tmp_path / "kg.kuzu"

    result = ingest_pipeline.ingest_paths(
        [docs / "overview.md"],
        project_id="proj_test",
        workspace_root=workspace,
        vdb_path=vdb_path,
        kg_path=kg_path,
        scope="local",
        embedder=StubEmbedder(),
    )

    assert result.files_processed == 1
    assert result.files_skipped == 0
    assert result.chunks_upserted >= 1
    assert result.nodes_upserted >= 1
    assert not result.errors


def test_ingest_python_file(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    src = workspace / "src"
    src.mkdir()
    (src / "service.py").write_text(
        "def authenticate(token: str) -> bool:\n    return bool(token)\n\n"
        "class AuthService:\n    pass\n"
    )

    result = ingest_pipeline.ingest_paths(
        [src / "service.py"],
        project_id="proj_test",
        workspace_root=workspace,
        vdb_path=tmp_path / "vdb.lance",
        kg_path=tmp_path / "kg.kuzu",
        scope="local",
        embedder=StubEmbedder(),
    )

    assert result.files_processed == 1
    assert result.chunks_upserted >= 1
    assert result.nodes_upserted >= 1  # at least one module node


def test_ingest_idempotent(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    f = workspace / "doc.md"
    f.write_text("# Title\nContent here.\n")

    kwargs = dict(
        paths=[f],
        project_id="proj_idempotent",
        workspace_root=workspace,
        vdb_path=tmp_path / "vdb.lance",
        kg_path=tmp_path / "kg.kuzu",
        scope="local",
        embedder=StubEmbedder(),
    )

    r1 = ingest_pipeline.ingest_paths(**kwargs)
    r2 = ingest_pipeline.ingest_paths(**kwargs)

    assert r1.chunks_upserted == r2.chunks_upserted
    assert r1.nodes_upserted == r2.nodes_upserted


def test_ingest_skips_unsupported_extension(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    unknown = workspace / "file.xyz"
    unknown.write_text("not supported")

    result = ingest_pipeline.ingest_paths(
        [unknown],
        project_id="proj_test",
        workspace_root=workspace,
        vdb_path=tmp_path / "vdb.lance",
        kg_path=tmp_path / "kg.kuzu",
        scope="local",
        embedder=StubEmbedder(),
    )

    assert result.files_processed == 0
    assert result.files_skipped == 1


def test_ingest_skips_binary_formats(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    pdf = workspace / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf content")

    result = ingest_pipeline.ingest_paths(
        [pdf],
        project_id="proj_test",
        workspace_root=workspace,
        vdb_path=tmp_path / "vdb.lance",
        kg_path=tmp_path / "kg.kuzu",
        scope="local",
        embedder=StubEmbedder(),
    )

    assert result.files_skipped == 1
    assert result.files_processed == 0


def test_ingest_directory(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "a.md").write_text("# A\ncontent a")
    (workspace / "b.py").write_text("def b():\n    pass\n")
    (workspace / "c.ts").write_text("export function c() {}\n")

    result = ingest_pipeline.ingest_directory(
        workspace,
        project_id="proj_dir",
        workspace_root=workspace,
        vdb_path=tmp_path / "vdb.lance",
        kg_path=tmp_path / "kg.kuzu",
        scope="local",
        embedder=StubEmbedder(),
    )

    assert result.files_processed == 3
    assert result.chunks_upserted >= 3
