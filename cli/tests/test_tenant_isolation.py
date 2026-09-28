"""Tests for tenant isolation enforcement.

Tenant isolation is a hard requirement: a recall query must never return results
from a project in a different tenant, even if both projects are on the same machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cartographer import config as config_mod, registry


def _write_config(workspace: Path, project_id: str, tenant: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=project_id, name=f"project-{project_id}"),
        isolation=config_mod.IsolationSection(tenant=tenant),
    )
    config_mod.save_config(workspace, cfg)


def test_recall_blocks_cross_tenant(tmp_path, monkeypatch):
    """recall command must exit with code 1 when project tenant and registry tenant differ."""
    from typer.testing import CliRunner
    from cartographer.cli import app

    workspace = tmp_path / "project"
    _write_config(workspace, "proj_abc", "team-a")

    # Register the project with a DIFFERENT tenant
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project(
        project_id="proj_abc",
        name="project-proj_abc",
        topology="local",
        tenant="team-b",  # mismatch
        location=workspace,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["recall", "some query", "--path", str(workspace)])

    assert result.exit_code != 0
    assert "tenant" in result.output.lower()


def test_recall_allows_same_tenant(tmp_path, monkeypatch):
    """recall should not block when tenants match (may fail for other reasons, not isolation)."""
    from typer.testing import CliRunner
    from cartographer.cli import app

    workspace = tmp_path / "project"
    _write_config(workspace, "proj_xyz", "team-a")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project(
        project_id="proj_xyz",
        name="project-proj_xyz",
        topology="local",
        tenant="team-a",  # match
        location=workspace,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["recall", "some query", "--path", str(workspace)])

    # May fail with exit code 0 (no results) or 1 (embedding not installed),
    # but must not fail with the "tenant mismatch" message
    assert "tenant mismatch" not in result.output.lower()


def test_list_projects_filters_by_tenant(tmp_path, monkeypatch):
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)

    registry.register_project("p1", "P1", "local", "team-a", tmp_path / "p1")
    registry.register_project("p2", "P2", "local", "team-b", tmp_path / "p2")
    registry.register_project("p3", "P3", "local", "team-a", tmp_path / "p3")

    team_a = registry.list_projects(tenant="team-a")
    team_b = registry.list_projects(tenant="team-b")

    assert len(team_a) == 2
    assert len(team_b) == 1
    assert all(p.tenant == "team-a" for p in team_a)
    assert all(p.tenant == "team-b" for p in team_b)


def test_list_projects_no_filter_returns_all(tmp_path, monkeypatch):
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)

    registry.register_project("x1", "X1", "local", "team-x", tmp_path / "x1")
    registry.register_project("x2", "X2", "local", "team-y", tmp_path / "x2")

    all_projects = registry.list_projects()
    assert len(all_projects) == 2
