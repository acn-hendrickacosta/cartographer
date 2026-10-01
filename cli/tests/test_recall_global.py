"""Phase 2 global recall spec: local-first read with central fallback.

These tests define the contract for `cartographer recall` in central topology.
They are intentionally RED until recall.py is wired to query the central index.

Reference implementation: cli/src/cartographer/runtime/scripts/user_prompt_submit.py
already has the local-first + merge + origin-tag pattern. recall.py needs to adopt it.

Contract (7 invariants):
  1. Local-only topology  → only local VDB/KG queried; central drivers never called.
  2. Central topology     → local queried first, then central; both VDB and KG queried.
  3. Origin tagging       → every result section is tagged with its origin (local/global).
  4. Local-first order    → local results appear before global in merged output, regardless of score.
  5. Deduplication        → same artifact path in both indexes appears once; LOCAL shadows global
                            regardless of score (per DATA_MODEL.md: "local results shadow global
                            results for the same artifact identity").
  6. Graceful degradation → central unreachable → local results returned with a warning;
                            command exits 0, not 1.
  7. Tenant isolation     → tenant mismatch blocks before any central query is attempted.

Merge algorithm (from user_prompt_submit.py reference):
  local_paths = {h.get("path") for h in local_hits}
  merged = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]
  for hit in merged:
      origin = hit.get("origin", "local")
      entry = f"[{hit.get('artifact_type', '')}|{origin}] {hit.get('path', '')}\\n{hit.get('text', '')}\\n"
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from cartographer import config as config_mod, registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(workspace: Path, project_id: str, topology: str = "local", tenant: str = "default") -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name=f"project-{project_id}"),
        topology=config_mod.TopologySection(mode=topology),
        isolation=config_mod.IsolationSection(tenant=tenant),
    )
    config_mod.save_config(workspace, cfg)


def _local_hit(path: str, score: float = 0.9) -> dict:
    return {"path": path, "text": "local content body", "score": score, "artifact_type": "code"}


def _global_hit(path: str, score: float = 0.8) -> dict:
    return {"path": path, "text": "global content body", "score": score, "artifact_type": "code"}


def _invoke(workspace: Path, query: str = "test query") -> "Result":
    from typer.testing import CliRunner
    from cartographer.cli import app
    return CliRunner().invoke(app, ["recall", query, "--path", str(workspace)])


def _setup_project(tmp_path: Path, project_id: str, topology: str, tenant: str = "default") -> Path:
    workspace = tmp_path / "proj"
    _write_config(workspace, project_id, topology=topology, tenant=tenant)
    (workspace / ".cartographer" / "local").mkdir(parents=True, exist_ok=True)
    return workspace


# ---------------------------------------------------------------------------
# 1. Local-only topology: central drivers never called
# ---------------------------------------------------------------------------

def test_local_topology_never_calls_central(tmp_path, monkeypatch):
    """In local topology, central driver factories must not be instantiated or queried."""
    workspace = _setup_project(tmp_path, "proj_local_001", topology="local")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_local_001", "proj", "local", "default", workspace)

    get_central_vdb = MagicMock()
    get_central_kg = MagicMock()

    with patch("cartographer.indexing.central.get_central_vdb", get_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", get_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        _invoke(workspace)

    get_central_vdb.assert_not_called()
    get_central_kg.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Central topology: both local and central VDB are queried
# ---------------------------------------------------------------------------

def test_central_topology_queries_central_vdb(tmp_path, monkeypatch):
    """In central topology, recall must call central VDB query with the project_id."""
    workspace = _setup_project(tmp_path, "proj_central_001", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_001", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    mock_central_vdb.query.return_value = [_global_hit("src/service.py")]

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    # Central VDB must be called with the project_id as first positional arg and a tombstone filter
    mock_central_vdb.query.assert_called_once_with(
        "proj_central_001", embedding=ANY, k=ANY, where=ANY
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 3. Origin tagging: results carry origin=local or origin=global labels
# ---------------------------------------------------------------------------

def test_results_tagged_with_origin(tmp_path, monkeypatch):
    """Every result section in central topology output must indicate its origin."""
    workspace = _setup_project(tmp_path, "proj_central_002", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_002", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    mock_central_vdb.query.return_value = [_global_hit("src/service.py")]

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    out = result.output.lower()
    # Either "[type|local]" style (hook format) or "origin=local" style (CLI debug format)
    has_local_tag = "|local]" in result.output or "origin=local" in out
    has_global_tag = "|global]" in result.output or "origin=global" in out
    assert has_local_tag, f"Expected local origin tag in output:\n{result.output}"
    assert has_global_tag, f"Expected global origin tag in output:\n{result.output}"


# ---------------------------------------------------------------------------
# 4. Local-first ordering: local appears before global, regardless of score
# ---------------------------------------------------------------------------

def test_local_results_appear_before_global(tmp_path, monkeypatch):
    """Local results must appear before global results even when global has a higher score."""
    workspace = _setup_project(tmp_path, "proj_central_003", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_003", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    # Global result has a higher score — local must still appear first
    mock_central_vdb.query.return_value = [_global_hit("src/global_service.py", score=0.99)]

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/local_main.py", score=0.5)]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    local_pos = result.output.find("local_main.py")
    global_pos = result.output.find("global_service.py")

    assert local_pos != -1, "local result not found in output"
    assert global_pos != -1, "global result not found in output"
    assert local_pos < global_pos, (
        f"local result must appear before global regardless of score "
        f"(local_pos={local_pos}, global_pos={global_pos})"
    )


# ---------------------------------------------------------------------------
# 5. Deduplication: local shadows global for the same path, regardless of score
# ---------------------------------------------------------------------------

def test_deduplication_local_shadows_global(tmp_path, monkeypatch):
    """A path in both indexes appears once; the LOCAL version wins regardless of score.

    Per DATA_MODEL.md: 'Local results shadow global results for the same artifact
    identity. This ensures that unmerged working state takes precedence over the
    last-promoted version of the same artifact.'

    Reference merge (user_prompt_submit.py):
        local_paths = {h.get("path") for h in local_hits}
        merged = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]
    """
    workspace = _setup_project(tmp_path, "proj_central_004", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_004", "proj", "central", "default", workspace)

    shared_path = "src/shared_module.py"

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    # Global has higher score — but local must still shadow it
    mock_central_vdb.query.return_value = [_global_hit(shared_path, score=0.99)]

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit(shared_path, score=0.5)]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    # Path appears exactly once as a result entry (dedup happened)
    # Count lines where the path appears as the result-entry path (not inside text body)
    path_lines = [l for l in result.output.splitlines() if shared_path in l]
    assert len(path_lines) == 1, (
        f"Expected {shared_path} in exactly one output line, got {len(path_lines)}:\n{result.output}"
    )

    # The LOCAL version must be what appears — "local content body" not "global content body"
    assert "local content body" in result.output, (
        f"Expected local version to shadow global version:\n{result.output}"
    )
    assert "global content body" not in result.output, (
        f"Global content leaked through despite local shadow rule:\n{result.output}"
    )


# ---------------------------------------------------------------------------
# 6. Graceful degradation: central unreachable → local results + warning, exit 0
# ---------------------------------------------------------------------------

def test_central_unreachable_returns_local_results(tmp_path, monkeypatch):
    """When central backend is unreachable, local results are returned and exit code is 0."""
    workspace = _setup_project(tmp_path, "proj_central_005", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_005", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = False

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = False

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    assert result.exit_code == 0
    assert "src/main.py" in result.output
    # Must NOT have called central query since is_reachable returned False
    mock_central_vdb.query.assert_not_called()
    # Must warn the user that central was skipped
    out = result.output.lower()
    assert "central" in out or "unreachable" in out, (
        f"Expected a warning about central being unreachable:\n{result.output}"
    )


def test_central_connection_exception_does_not_crash(tmp_path, monkeypatch):
    """An exception raised by the central driver must not crash recall — degrade gracefully."""
    workspace = _setup_project(tmp_path, "proj_central_006", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_006", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.side_effect = Exception("connection refused")

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    assert result.exit_code == 0
    assert "src/main.py" in result.output


# ---------------------------------------------------------------------------
# 7. Tenant isolation gate fires before any central query
# ---------------------------------------------------------------------------

def test_tenant_mismatch_blocks_before_central_query(tmp_path, monkeypatch):
    """Tenant isolation gate must fire before any central query is attempted.

    recall.py already enforces this for local (line 36-40). This test confirms
    the gate still applies when the project is configured for central topology.
    """
    workspace = _setup_project(tmp_path, "proj_central_007", topology="central", tenant="team-a")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    # Registry has a different tenant than the local config — mismatch
    registry.register_project("proj_central_007", "proj", "central", "team-b", workspace)

    mock_central_vdb = MagicMock()

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb):
        result = _invoke(workspace)

    assert result.exit_code != 0
    assert "tenant" in result.output.lower()
    mock_central_vdb.query.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Tombstone filter: recall never returns tombstoned global artifacts
# ---------------------------------------------------------------------------

def test_tombstoned_artifacts_excluded_from_global_recall(tmp_path, monkeypatch):
    """recall must pass a tombstone filter so tombstoned chunks are excluded.

    The PgvectorDriver.query already hard-filters is_tombstone=FALSE.
    This test verifies recall.py passes a where clause that makes intent explicit
    and that tombstoned results from the mock are not surfaced.
    """
    workspace = _setup_project(tmp_path, "proj_central_008", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_008", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    # Driver returns nothing because tombstoned chunks are filtered server-side
    mock_central_vdb.query.return_value = []

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[_local_hit("src/main.py")]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    # Verify recall passes a tombstone where-clause to the central VDB driver
    call_kwargs = mock_central_vdb.query.call_args
    assert call_kwargs is not None, "central VDB query was not called"
    where_arg = call_kwargs.kwargs.get("where", "")
    assert "is_tombstone" in where_arg, (
        f"recall must pass a tombstone filter; got where={where_arg!r}"
    )
    assert result.exit_code == 0


def test_tombstone_filter_does_not_exclude_live_results(tmp_path, monkeypatch):
    """A non-tombstoned global result must still appear in recall output."""
    workspace = _setup_project(tmp_path, "proj_central_009", topology="central")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project("proj_central_009", "proj", "central", "default", workspace)

    mock_central_vdb = MagicMock()
    mock_central_vdb.is_reachable.return_value = True
    # Driver returns a live (non-tombstoned) result
    live_hit = _global_hit("src/live_service.py")
    mock_central_vdb.query.return_value = [live_hit]

    mock_central_kg = MagicMock()
    mock_central_kg.is_reachable.return_value = True
    mock_central_kg.query.return_value = []

    with patch("cartographer.indexing.central.get_central_vdb", return_value=mock_central_vdb), \
         patch("cartographer.indexing.central.get_central_kg", return_value=mock_central_kg), \
         patch("cartographer.indexing.vdb.query", return_value=[]), \
         patch("cartographer.indexing.kg.query", return_value=[]), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = _invoke(workspace)

    assert "live_service.py" in result.output, (
        f"Live global result must appear in output:\n{result.output}"
    )
    assert result.exit_code == 0
