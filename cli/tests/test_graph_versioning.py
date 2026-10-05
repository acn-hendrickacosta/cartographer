"""Phase 4: graph versioning — PromotionRecord history and `cartographer log`.

PromotionRecord is deliberately a separate, append-only node type in the
central KG — not registry.ProjectRecord.last_promoted_sha, which is a single
value overwritten on every promote and used as Phase 3.3's rename-detection
diff base. Conflating the two would break that diff-since-last-promote
semantics the moment history needs to look further back than the latest
promote. See kg_neo4j.Neo4jDriver.record_promotion's docstring.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cartographer import config as config_mod
from cartographer.cli import app


def _setup_central_project(workspace, project_id: str) -> None:
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name="log-test"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)


def test_log_lists_promotion_history(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    _setup_central_project(workspace, "proj_log_001")

    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True
    central_kg.list_promotions.return_value = [
        {"commit_sha": "abc123def456", "promoted_at": "2026-01-02T00:00:00+00:00", "node_count": 15, "edge_count": 8},
        {"commit_sha": "sha1sha1sha1", "promoted_at": "2026-01-01T00:00:00+00:00", "node_count": 10, "edge_count": 5},
    ]

    with patch("cartographer.indexing.central.get_central_kg", return_value=central_kg):
        result = CliRunner().invoke(app, ["log", "--path", str(workspace)])

    assert result.exit_code == 0, result.output
    central_kg.list_promotions.assert_called_once_with("proj_log_001")
    assert "abc123def456"[:12] in result.output
    assert "15" in result.output
    assert "8" in result.output


def test_log_reports_no_history_yet(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    _setup_central_project(workspace, "proj_log_002")

    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True
    central_kg.list_promotions.return_value = []

    with patch("cartographer.indexing.central.get_central_kg", return_value=central_kg):
        result = CliRunner().invoke(app, ["log", "--path", str(workspace)])

    assert result.exit_code == 0
    assert "no promotion history" in result.output


def test_promote_records_promotion_history(tmp_path, monkeypatch):
    """promote.py must call record_promotion after a successful promote, with
    the SAME last_promoted_sha it just wrote to the registry, and the total
    post-promotion graph size (not this promotion's own delta)."""
    from cartographer import registry
    from cartographer.indexing import kg as kg_driver, vdb as vdb_driver
    from cartographer.indexing.vdb import ChunkRecord

    project_id = "proj_log_004"
    workspace = tmp_path / "proj"
    workspace.mkdir()
    import subprocess
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=workspace, check=True, capture_output=True)
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True)
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()

    _setup_central_project(workspace, project_id)
    override = config_mod.LocalOverrideConfig(promotion_token="test-token")
    config_mod.save_local_override(workspace, override)

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    chunk = ChunkRecord(
        id=f"{project_id}/a.py:0", project_id=project_id, scope="local",
        artifact_type="code", path="a.py", origin="local",
        text="x = 1", embedding=[0.1] * 384, updated_at="2026-01-01T00:00:00+00:00",
    )
    vdb_driver.upsert(local_dir / "vdb.lance", "local", [chunk])
    kg_driver.ensure_namespace(local_dir / "kg.kuzu")

    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry.json")
    registry.register_project(project_id, "log-test", "central", "default", workspace)

    central_vdb = MagicMock()
    central_vdb.is_reachable.return_value = True
    central_vdb.query_all_paths.return_value = []
    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True
    central_kg.namespace_stats.return_value = {"nodes": 42, "edges": 17}

    with patch("cartographer.commands.promote.get_central_vdb", return_value=central_vdb), \
         patch("cartographer.commands.promote.get_central_kg", return_value=central_kg):
        result = CliRunner().invoke(app, ["promote", "--path", str(workspace), "--full"])

    assert result.exit_code == 0, result.output
    central_kg.record_promotion.assert_called_once()
    call_args = central_kg.record_promotion.call_args.args
    assert call_args[0] == project_id
    assert call_args[1] == head_sha
    assert call_args[3] == 42  # node_count from namespace_stats, not this promote's own delta
    assert call_args[4] == 17

    # and record.last_promoted_sha matches the same commit_sha passed to record_promotion
    updated = registry.get_project(project_id)
    assert updated.last_promoted_sha == head_sha


def test_log_local_topology_reports_no_history(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_log_003", name="log-test"),
        topology=config_mod.TopologySection(mode="local"),
    )
    config_mod.save_config(workspace, cfg)

    result = CliRunner().invoke(app, ["log", "--path", str(workspace)])
    assert result.exit_code == 0
    assert "local-only" in result.output
