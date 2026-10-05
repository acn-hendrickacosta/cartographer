"""Phase 3.3: rename tracking — git rename detection in promote.py, supersedes
edges in the global KG, last_promoted_sha tracking, and recall's redirect.

Uses a real git repo (rename detection needs real `git diff --name-status`
output) and real local LanceDB/Kuzu fixtures, with central_vdb/central_kg
mocked — the central backends are exercised separately in
test_central_drivers.py's integration tests.

Patches get_central_vdb/get_central_kg at cartographer.commands.promote (where
promote.py imports them via `from X import Y` at module level), not at
cartographer.indexing.central — patching the latter only takes effect for
callers that import locally inside their function body (like recall.py).
Patching the original module's attribute does not reach a name already bound
at module-import time elsewhere.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cartographer import config as config_mod, registry
from cartographer.indexing import kg, vdb
from cartographer.indexing.kg import Node
from cartographer.indexing.vdb import ChunkRecord


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _setup_repo_with_rename(tmp_path: Path, project_id: str) -> tuple[Path, str, str]:
    """Create a real git repo: commit old_path, capture that SHA, then rename
    old_path -> new_path and commit again. Returns (workspace, pre_rename_sha, old_path)."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    _git("init", cwd=workspace)
    _git("config", "user.email", "test@example.com", cwd=workspace)
    _git("config", "user.name", "Test", cwd=workspace)

    old_path = workspace / "src" / "old_name.py"
    old_path.parent.mkdir(parents=True)
    old_path.write_text("def hello(): pass\n", encoding="utf-8")
    _git("add", "src/old_name.py", cwd=workspace)
    _git("commit", "-m", "add old_name.py", cwd=workspace)
    pre_rename_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True
    ).strip()

    _git("mv", "src/old_name.py", "src/new_name.py", cwd=workspace)
    _git("commit", "-m", "rename to new_name.py", cwd=workspace)

    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name="rename-test"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)
    override = config_mod.LocalOverrideConfig(promotion_token="test-token")
    config_mod.save_local_override(workspace, override)

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    vdb_path = local_dir / "vdb.lance"
    kg_path = local_dir / "kg.kuzu"

    chunk = ChunkRecord(
        id=f"{project_id}/src/new_name.py:0", project_id=project_id, scope="local",
        artifact_type="code", path="src/new_name.py", origin="local",
        text="def hello(): pass", embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    vdb.upsert(vdb_path, "local", [chunk])
    kg.ensure_namespace(kg_path)
    kg.upsert_nodes(kg_path, [Node(
        id="path:src/new_name.py", project_id=project_id, scope="local",
        type="module", path="src/new_name.py", attrs="{}",
    )])

    return workspace, pre_rename_sha, "src/old_name.py"


def _mock_central(global_paths: list[str]):
    central_vdb = MagicMock()
    central_vdb.is_reachable.return_value = True
    central_vdb.query_all_paths.return_value = global_paths

    central_kg = MagicMock()
    central_kg.is_reachable.return_value = True

    return central_vdb, central_kg


def _invoke_promote(workspace: Path, dry_run: bool = False):
    from cartographer.cli import app
    args = ["promote", "--path", str(workspace), "--full"]
    if dry_run:
        args.append("--dry-run")
    return CliRunner().invoke(app, args)


def _patch_central(central_vdb, central_kg):
    return (
        patch("cartographer.commands.promote.get_central_vdb", return_value=central_vdb),
        patch("cartographer.commands.promote.get_central_kg", return_value=central_kg),
    )


# ---------------------------------------------------------------------------
# Rename detection writes a supersedes edge and tombstones the old path
# ---------------------------------------------------------------------------

def test_rename_writes_supersedes_edge_and_tombstones_old_path(tmp_path, monkeypatch):
    project_id = "proj_rename_001"
    workspace, pre_rename_sha, old_path = _setup_repo_with_rename(tmp_path, project_id)

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    record = registry.register_project(project_id, "rename-test", "central", "default", workspace)
    record.last_promoted_sha = pre_rename_sha
    registry.upsert_project(record)

    central_vdb, central_kg = _mock_central(global_paths=[old_path])
    p_vdb, p_kg = _patch_central(central_vdb, central_kg)
    with p_vdb, p_kg:
        result = _invoke_promote(workspace)

    assert result.exit_code == 0, result.output

    # supersedes edge written: new_name.py -> old_name.py
    edge_calls = central_kg.upsert_edges.call_args_list
    assert len(edge_calls) == 1
    edges = edge_calls[0].args[0]
    assert len(edges) == 1
    edge = edges[0]
    assert edge.type == "supersedes"
    assert "src/old_name.py" in edge.dst
    assert "src/new_name.py" in edge.src
    attrs = json.loads(edge.attrs)
    assert attrs["renamed_from"] == old_path

    # old path tombstoned in both KG and VDB
    central_kg.set_tombstoned.assert_called_once()
    assert central_kg.set_tombstoned.call_args.args[0] == old_path
    central_vdb.tombstone_path.assert_called_once_with(project_id, old_path)

    # last_promoted_sha advanced to the post-rename HEAD
    updated = registry.get_project(project_id)
    new_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
    assert updated.last_promoted_sha == new_head
    assert updated.last_promoted_sha != pre_rename_sha


def test_renamed_path_excluded_from_plain_tombstone_detection(tmp_path, monkeypatch):
    """The renamed old path must not also appear in the plain-deletion tombstone set."""
    project_id = "proj_rename_002"
    workspace, pre_rename_sha, old_path = _setup_repo_with_rename(tmp_path, project_id)

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    record = registry.register_project(project_id, "rename-test", "central", "default", workspace)
    record.last_promoted_sha = pre_rename_sha
    registry.upsert_project(record)

    central_vdb, central_kg = _mock_central(global_paths=[old_path])
    p_vdb, p_kg = _patch_central(central_vdb, central_kg)
    with p_vdb, p_kg:
        result = _invoke_promote(workspace)

    assert result.exit_code == 0, result.output
    # tombstone_path for old_path happens exactly once (from the rename path),
    # not twice (which would indicate it was ALSO caught as a plain deletion)
    assert central_vdb.tombstone_path.call_count == 1


def test_dry_run_reports_rename_without_writing(tmp_path, monkeypatch):
    project_id = "proj_rename_003"
    workspace, pre_rename_sha, old_path = _setup_repo_with_rename(tmp_path, project_id)

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    record = registry.register_project(project_id, "rename-test", "central", "default", workspace)
    record.last_promoted_sha = pre_rename_sha
    registry.upsert_project(record)

    central_vdb, central_kg = _mock_central(global_paths=[old_path])
    p_vdb, p_kg = _patch_central(central_vdb, central_kg)
    with p_vdb, p_kg:
        result = _invoke_promote(workspace, dry_run=True)

    assert result.exit_code == 0, result.output
    assert "src/old_name.py -> src/new_name.py" in result.output
    central_kg.upsert_edges.assert_not_called()
    central_kg.set_tombstoned.assert_not_called()
    central_vdb.tombstone_path.assert_not_called()

    # last_promoted_sha must not advance on a dry run
    updated = registry.get_project(project_id)
    assert updated.last_promoted_sha == pre_rename_sha


def test_no_prior_sha_falls_back_to_delete_plus_add(tmp_path, monkeypatch):
    """When last_promoted_sha is empty (first promote, or git unavailable),
    rename detection is skipped — old path is treated as a plain deletion."""
    project_id = "proj_rename_004"
    workspace, _pre_rename_sha, old_path = _setup_repo_with_rename(tmp_path, project_id)

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    record = registry.register_project(project_id, "rename-test", "central", "default", workspace)
    # last_promoted_sha left empty — simulates first promote ever
    registry.upsert_project(record)

    central_vdb, central_kg = _mock_central(global_paths=[old_path])
    p_vdb, p_kg = _patch_central(central_vdb, central_kg)
    with p_vdb, p_kg:
        result = _invoke_promote(workspace)

    assert result.exit_code == 0, result.output
    # no supersedes edge — old path tombstoned as a plain deletion instead
    central_kg.upsert_edges.assert_not_called()
    central_vdb.tombstone_path.assert_called_once_with(project_id, old_path)


def test_git_diff_failure_falls_back_with_warning(tmp_path, monkeypatch):
    """When last_promoted_sha is set but the git command itself fails (e.g. the
    SHA no longer exists after a rebase, or git is unavailable), rename
    detection must degrade to treating the path as a plain deletion — with a
    warning printed — rather than crashing promote."""
    project_id = "proj_rename_005"
    workspace, _pre_rename_sha, old_path = _setup_repo_with_rename(tmp_path, project_id)

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    record = registry.register_project(project_id, "rename-test", "central", "default", workspace)
    # A SHA that no longer exists in this repo's history
    record.last_promoted_sha = "0" * 40
    registry.upsert_project(record)

    central_vdb, central_kg = _mock_central(global_paths=[old_path])
    p_vdb, p_kg = _patch_central(central_vdb, central_kg)
    with p_vdb, p_kg:
        result = _invoke_promote(workspace)

    assert result.exit_code == 0, result.output
    assert "git rename detection unavailable" in result.output
    central_kg.upsert_edges.assert_not_called()
    central_vdb.tombstone_path.assert_called_once_with(project_id, old_path)
