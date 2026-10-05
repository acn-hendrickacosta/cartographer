"""Phase 4: edge taxonomy governance — lint_edge_types, the seed-time lint
step, --strict, config round-trip, and `cartographer taxonomy list`.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cartographer import config as config_mod, taxonomy
from cartographer.cli import app
from cartographer.indexing import kg as kg_driver
from cartographer.indexing import vdb as vdb_driver
from cartographer.indexing.kg import Edge, Node
from cartographer.ingestion.embedder import Embedder
from cartographer.ingestion.pipeline import ingest_paths


class StubEmbedder(Embedder):
    def __init__(self):
        self._model_name = "stub"
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]

    @property
    def dim(self) -> int:
        return 384


# ---------------------------------------------------------------------------
# taxonomy.lint_edge_types
# ---------------------------------------------------------------------------

def test_lint_edge_types_flags_unknown():
    unknown = taxonomy.lint_edge_types({"imports", "frobnicates"})
    assert unknown == {"frobnicates"}


def test_lint_edge_types_all_canonical_returns_empty():
    assert taxonomy.lint_edge_types({"calls", "imports", "extends"}) == set()


# ---------------------------------------------------------------------------
# cartographer taxonomy list
# ---------------------------------------------------------------------------

def test_taxonomy_list_command():
    result = CliRunner().invoke(app, ["taxonomy", "list"])
    assert result.exit_code == 0
    assert "supersedes" in result.output
    assert taxonomy.CANONICAL_TAXONOMY_VERSION in result.output


# ---------------------------------------------------------------------------
# config.py: [taxonomy] / [federation] round-trip
# ---------------------------------------------------------------------------

def test_config_round_trips_taxonomy_and_federation(tmp_path):
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="p", name="p"),
        taxonomy=config_mod.TaxonomySection(version="2.0"),
        federation=config_mod.FederationSection(global_overlays=["design-system"]),
    )
    config_mod.save_config(tmp_path, cfg)
    loaded = config_mod.load_config(tmp_path)

    assert loaded.taxonomy.version == "2.0"
    assert loaded.federation.global_overlays == ["design-system"]


def test_config_defaults_when_sections_absent(tmp_path):
    """A cartographer.toml written before Phase 4 (no [taxonomy]/[federation])
    must still load with sane defaults, not crash."""
    (tmp_path / "cartographer.toml").write_text(
        '[project]\nid = "p"\nname = "p"\n', encoding="utf-8",
    )
    loaded = config_mod.load_config(tmp_path)

    assert loaded.taxonomy.version == taxonomy.CANONICAL_TAXONOMY_VERSION
    assert loaded.federation.global_overlays == []


# ---------------------------------------------------------------------------
# Seed-time lint step: non-strict (warn + drop) vs. strict (fail the file)
# ---------------------------------------------------------------------------

def _seed_source(workspace: Path) -> Path:
    src = workspace / "src"
    src.mkdir(parents=True)
    f = src / "a.py"
    f.write_text("def hello():\n    pass\n", encoding="utf-8")
    return f


def test_ingest_drops_unknown_edge_type_by_default(tmp_path, monkeypatch):
    """Non-strict (default): an unknown edge type is dropped and reported as
    a warning, but the file still ingests successfully — known edges and all
    nodes still get written."""
    workspace = tmp_path / "proj"
    f = _seed_source(workspace)
    vdb_path = workspace / ".cartographer" / "local" / "vdb.lance"
    kg_path = workspace / ".cartographer" / "local" / "kg.kuzu"

    import cartographer.ingestion.graph_extractor as ge
    from cartographer.ingestion.text_extractor import ArtifactType

    def _fake_extract(**kwargs):
        return ge.ExtractedGraph(
            nodes=[
                Node(id="path:src/a.py", project_id="p", scope="local", type="module", path="src/a.py", attrs="{}"),
                Node(id="path:src/b.py", project_id="p", scope="local", type="module", path="src/b.py", attrs="{}"),
                Node(id="path:src/c.py", project_id="p", scope="local", type="module", path="src/c.py", attrs="{}"),
            ],
            edges=[
                Edge(src="path:src/a.py", dst="path:src/b.py", type="imports", scope="local", attrs="{}"),
                Edge(src="path:src/a.py", dst="path:src/c.py", type="frobnicates", scope="local", attrs="{}"),
            ],
        )

    monkeypatch.setattr(ge, "extract", _fake_extract)

    result = ingest_paths(
        [f], project_id="p", workspace_root=workspace,
        vdb_path=vdb_path, kg_path=kg_path, embedder=StubEmbedder(),
    )

    assert result.files_processed == 1
    assert result.errors == []
    assert len(result.taxonomy_warnings) == 1
    assert "frobnicates" in result.taxonomy_warnings[0]

    edges = kg_driver.query(kg_path, "MATCH ()-[r:RelatesTo]->() RETURN r.type AS type")
    assert {e["type"] for e in edges} == {"imports"}


def test_ingest_strict_fails_file_on_unknown_edge_type(tmp_path, monkeypatch):
    workspace = tmp_path / "proj"
    f = _seed_source(workspace)
    vdb_path = workspace / ".cartographer" / "local" / "vdb.lance"
    kg_path = workspace / ".cartographer" / "local" / "kg.kuzu"

    import cartographer.ingestion.graph_extractor as ge

    def _fake_extract(**kwargs):
        return ge.ExtractedGraph(
            nodes=[Node(id="path:src/a.py", project_id="p", scope="local", type="module", path="src/a.py", attrs="{}")],
            edges=[Edge(src="path:src/a.py", dst="path:src/c.py", type="frobnicates", scope="local", attrs="{}")],
        )

    monkeypatch.setattr(ge, "extract", _fake_extract)

    result = ingest_paths(
        [f], project_id="p", workspace_root=workspace,
        vdb_path=vdb_path, kg_path=kg_path, embedder=StubEmbedder(), strict=True,
    )

    assert result.files_processed == 0
    assert len(result.errors) == 1
    assert "frobnicates" in result.errors[0]
    assert result.taxonomy_warnings == []


# ---------------------------------------------------------------------------
# cartographer doctor: taxonomy version pin + local KG drift
# ---------------------------------------------------------------------------

def test_doctor_reports_taxonomy_version_drift(tmp_path, monkeypatch):
    monkeypatch.setattr("cartographer.registry.registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    workspace = tmp_path / "proj"
    CliRunner().invoke(app, ["init", "--path", str(workspace)])

    cfg = config_mod.load_config(workspace)
    cfg.taxonomy.version = "0.1"
    config_mod.save_config(workspace, cfg)

    result = CliRunner().invoke(app, ["doctor", "--path", str(workspace)])
    assert "taxonomy version drift" in result.output
    assert "0.1" in result.output


def test_doctor_taxonomy_matches_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("cartographer.registry.registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    workspace = tmp_path / "proj"
    CliRunner().invoke(app, ["init", "--path", str(workspace)])

    result = CliRunner().invoke(app, ["doctor", "--path", str(workspace)])
    assert "edge taxonomy pinned version" in result.output
    assert "drift" not in result.output
