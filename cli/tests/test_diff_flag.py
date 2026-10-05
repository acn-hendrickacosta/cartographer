"""Phase 4: CI/CD freshness integration — `cartographer seed --diff` and
`cartographer promote --diff`.

Both reuse a real git repo (git diff needs real history) and reconcile with
Phase 3.3's existing last_promoted_sha field via a shared 'auto' sentinel
rather than introducing a second, parallel notion of "the baseline to diff
against" — see the Phase 4 doc alignment note this design follows.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cartographer import config as config_mod, registry
from cartographer.cli import app


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo_with_two_commits(tmp_path: Path) -> tuple[Path, str]:
    """Commit a.py and b.py, capture that SHA, then edit a.py and commit again.
    Returns (workspace, pre_edit_sha)."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    _git("init", cwd=workspace)
    _git("config", "user.email", "t@example.com", cwd=workspace)
    _git("config", "user.name", "T", cwd=workspace)

    src = workspace / "src"
    src.mkdir()
    (src / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    (src / "b.py").write_text("def b(): pass\n", encoding="utf-8")
    _git("add", "-A", cwd=workspace)
    _git("commit", "-m", "initial", cwd=workspace)
    pre_edit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()

    (src / "a.py").write_text("def a(): pass\ndef a2(): pass\n", encoding="utf-8")
    _git("add", "-A", cwd=workspace)
    _git("commit", "-m", "edit a.py", cwd=workspace)

    return workspace, pre_edit_sha


# ---------------------------------------------------------------------------
# cartographer seed --diff
# ---------------------------------------------------------------------------

def test_seed_diff_ingests_only_changed_files(tmp_path, monkeypatch):
    workspace, pre_edit_sha = _init_repo_with_two_commits(tmp_path)

    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    runner = CliRunner()
    runner.invoke(app, ["init", "--path", str(workspace), "--stacks", "python"])

    monkeypatch.setattr("cartographer.ingestion.embedder.get_embedder", lambda: _stub_embedder())
    monkeypatch.setattr("cartographer.commands.seed._serve_reachable", lambda port: False)

    result = runner.invoke(app, ["seed", "--path", str(workspace), "--diff", pre_edit_sha])
    assert result.exit_code == 0, result.output
    assert "1 of" in result.output  # only a.py changed, out of however many discovered
    assert "processed: 1" in result.output


def test_seed_diff_auto_falls_back_without_last_promoted_sha(tmp_path, monkeypatch):
    workspace, _pre_edit_sha = _init_repo_with_two_commits(tmp_path)

    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    runner = CliRunner()
    runner.invoke(app, ["init", "--path", str(workspace), "--stacks", "python"])

    monkeypatch.setattr("cartographer.ingestion.embedder.get_embedder", lambda: _stub_embedder())
    monkeypatch.setattr("cartographer.commands.seed._serve_reachable", lambda port: False)

    result = runner.invoke(app, ["seed", "--path", str(workspace), "--diff", "auto"])
    assert result.exit_code == 0, result.output
    assert "no last_promoted_sha recorded yet" in result.output


def test_seed_requires_source_unless_diff_given(tmp_path, monkeypatch):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    runner = CliRunner()
    runner.invoke(app, ["init", "--path", str(workspace)])

    result = runner.invoke(app, ["seed", "--path", str(workspace)])
    assert result.exit_code == 2
    assert "source is required" in result.output


def _stub_embedder():
    from cartographer.ingestion.embedder import Embedder

    class _Stub(Embedder):
        def __init__(self):
            self._model_name = "stub"
            self._model = None

        def embed(self, texts):
            return [[0.1] * 384 for _ in texts]

        @property
        def dim(self):
            return 384

    return _Stub()


# ---------------------------------------------------------------------------
# cartographer promote --diff
# ---------------------------------------------------------------------------

def _setup_central_project(workspace: Path, project_id: str) -> None:
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name="diff-test"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)
    override = config_mod.LocalOverrideConfig(promotion_token="test-token")
    config_mod.save_local_override(workspace, override)


def test_promote_diff_only_promotes_changed_paths(tmp_path, monkeypatch):
    from cartographer.indexing import kg as kg_driver, vdb as vdb_driver
    from cartographer.indexing.vdb import ChunkRecord
    from cartographer.indexing.kg import Node

    project_id = "proj_diff_001"
    workspace, pre_edit_sha = _init_repo_with_two_commits(tmp_path)
    _setup_central_project(workspace, project_id)

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    chunk_a = ChunkRecord(
        id=f"{project_id}/src/a.py:0", project_id=project_id, scope="local",
        artifact_type="code", path="src/a.py", origin="local",
        text="def a(): pass\ndef a2(): pass", embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    chunk_b = ChunkRecord(
        id=f"{project_id}/src/b.py:0", project_id=project_id, scope="local",
        artifact_type="code", path="src/b.py", origin="local",
        text="def b(): pass", embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    vdb_driver.upsert(local_dir / "vdb.lance", "local", [chunk_a, chunk_b])
    kg_driver.ensure_namespace(local_dir / "kg.kuzu")
    kg_driver.upsert_nodes(local_dir / "kg.kuzu", [
        Node(id="path:src/a.py", project_id=project_id, scope="local", type="module", path="src/a.py", attrs="{}"),
        Node(id="path:src/b.py", project_id=project_id, scope="local", type="module", path="src/b.py", attrs="{}"),
    ])

    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    registry.register_project(project_id, "diff-test", "central", "default", workspace)

    central_vdb = MagicMock()
    central_vdb.is_reachable.return_value = True
    central_vdb.query_all_paths.return_value = []
    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True

    with patch("cartographer.commands.promote.get_central_vdb", return_value=central_vdb), \
         patch("cartographer.commands.promote.get_central_kg", return_value=central_kg):
        result = CliRunner().invoke(app, [
            "promote", "--path", str(workspace), "--diff", pre_edit_sha,
        ])

    assert result.exit_code == 0, result.output
    assert "mode:     diff" in result.output

    upserted_paths = {c.path for call in central_vdb.upsert.call_args_list for c in call.args[1]}
    assert upserted_paths == {"src/a.py"}


def test_promote_diff_auto_reuses_last_promoted_sha(tmp_path, monkeypatch):
    from cartographer.indexing import kg as kg_driver, vdb as vdb_driver
    from cartographer.indexing.vdb import ChunkRecord
    from cartographer.indexing.kg import Node

    project_id = "proj_diff_002"
    workspace, pre_edit_sha = _init_repo_with_two_commits(tmp_path)
    _setup_central_project(workspace, project_id)

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    chunk_a = ChunkRecord(
        id=f"{project_id}/src/a.py:0", project_id=project_id, scope="local",
        artifact_type="code", path="src/a.py", origin="local",
        text="def a(): pass\ndef a2(): pass", embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    vdb_driver.upsert(local_dir / "vdb.lance", "local", [chunk_a])
    kg_driver.ensure_namespace(local_dir / "kg.kuzu")

    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    record = registry.register_project(project_id, "diff-test", "central", "default", workspace)
    record.last_promoted_sha = pre_edit_sha
    registry.upsert_project(record)

    central_vdb = MagicMock()
    central_vdb.is_reachable.return_value = True
    central_vdb.query_all_paths.return_value = []
    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True

    with patch("cartographer.commands.promote.get_central_vdb", return_value=central_vdb), \
         patch("cartographer.commands.promote.get_central_kg", return_value=central_kg):
        result = CliRunner().invoke(app, [
            "promote", "--path", str(workspace), "--diff", "auto",
        ])

    assert result.exit_code == 0, result.output
    assert f"mode:     diff (since {pre_edit_sha})" in result.output
