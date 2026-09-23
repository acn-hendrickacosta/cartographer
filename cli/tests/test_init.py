from pathlib import Path

from typer.testing import CliRunner

from cartographer import config as config_mod, registry
from cartographer.cli import app

runner = CliRunner()


def test_init_scaffolds_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python,react"])
    assert result.exit_code == 0, result.output

    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claude" / "standards" / "cross-stack").is_dir()
    assert (tmp_path / ".claude" / "standards" / "python").is_dir()
    assert (tmp_path / ".claude" / "standards" / "react").is_dir()
    assert (tmp_path / "cartographer.toml").exists()
    assert (tmp_path / "cartographer.local.toml").exists()
    assert (tmp_path / ".cartographer" / "local" / "vdb.lance").exists()
    assert (tmp_path / ".cartographer" / "local" / "kg.kuzu").exists()

    cfg = config_mod.load_config(tmp_path)
    assert cfg.stacks.active == ["cross-stack", "python", "react"]

    record = registry.get_project(cfg.project.id)
    assert record is not None
    assert record.name == tmp_path.name


def test_init_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    first = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert first.exit_code == 0, first.output
    first_config_text = (tmp_path / "cartographer.toml").read_text(encoding="utf-8")

    second = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert second.exit_code == 0, second.output

    second_config_text = (tmp_path / "cartographer.toml").read_text(encoding="utf-8")
    assert first_config_text == second_config_text

    backups = list((tmp_path / ".claude" / ".cartographer-backup").glob("*")) if (
        tmp_path / ".claude" / ".cartographer-backup"
    ).exists() else []
    assert backups == []

    registry_records = registry.load_registry()
    assert len(registry_records) == 1


def test_doctor_passes_after_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["doctor", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "all local checks passed" in result.output


def test_promote_is_noop_for_local_topology(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["promote", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "nothing to promote" in result.output
