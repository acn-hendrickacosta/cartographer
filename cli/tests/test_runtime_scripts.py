"""Tests for shared Claude Code hook-script helpers."""

from pathlib import Path

from cartographer.runtime.scripts import resolve_workspace


def test_resolve_workspace_uses_claude_project_dir(monkeypatch, tmp_path: Path) -> None:
    """Claude Code sets CLAUDE_PROJECT_DIR for every hook invocation — this is
    the real-world path with no CARTO_WORKSPACE override set."""
    monkeypatch.delenv("CARTO_WORKSPACE", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert resolve_workspace() == tmp_path.resolve()


def test_resolve_workspace_carto_workspace_overrides_claude_project_dir(monkeypatch, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CARTO_WORKSPACE", str(other))
    assert resolve_workspace() == other.resolve()


def test_resolve_workspace_falls_back_to_cwd(monkeypatch) -> None:
    monkeypatch.delenv("CARTO_WORKSPACE", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert resolve_workspace() == Path(".").resolve()
