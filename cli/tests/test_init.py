import json
from pathlib import Path

from typer.testing import CliRunner

from cartographer import config as config_mod, registry
from cartographer.cli import app

runner = CliRunner()


def _settings(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_init_rerun_preserves_fields_it_does_not_own(tmp_path: Path, monkeypatch) -> None:
    """Regression test: init.py used to rebuild cartographer.toml from scratch
    on every run, special-casing only topology.mode -- silently wiping any
    other field (registry_url, retrieval tuning, taxonomy version, federation
    overlays, ...) set outside of init. Found while building SR.2 when a
    second `init --stacks` run reset stacks.registry_url back to ""."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    first = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python"])
    assert first.exit_code == 0, first.output

    cfg = config_mod.load_config(tmp_path)
    # registry_url intentionally left unset here -- setting it would make this
    # init run actually attempt a registry fetch, which is covered separately
    # (test_stack_registry_fetch.py's real-server tests). This test is only
    # about config-field preservation across a re-run.
    cfg.stacks.registry_fallback = "error"
    cfg.retrieval.top_k = 42
    cfg.federation.global_overlays = ["design-system"]
    config_mod.save_config(tmp_path, cfg)

    second = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python"])
    assert second.exit_code == 0, second.output

    reloaded = config_mod.load_config(tmp_path)
    assert reloaded.stacks.registry_fallback == "error"
    assert reloaded.retrieval.top_k == 42
    assert reloaded.federation.global_overlays == ["design-system"]
    # stacks.active is the one StacksSection field init.py does own -- still updated correctly
    assert reloaded.stacks.active == ["cross-stack", "python"]


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


def test_init_wires_ingest_and_recall_hooks(tmp_path: Path, monkeypatch) -> None:
    """Without this, edited files never get re-ingested automatically — the
    project's whole premise is deterministic hooks instead of relying on
    someone (human or Claude) remembering to run `cartographer seed`."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    hooks = _settings(tmp_path)["hooks"]
    commands = {
        event: hooks[event][0]["hooks"][0]["command"]
        for event in ("PostToolUse", "Stop", "SessionStart", "UserPromptSubmit")
    }
    assert commands == {
        "PostToolUse": "cartographer hook enqueue",
        "Stop": "cartographer hook flush",
        "SessionStart": "cartographer hook preload",
        "UserPromptSubmit": "cartographer hook retrieve",
    }


def test_init_hooks_survive_rerun_without_duplicating(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path)])
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    hooks = _settings(tmp_path)["hooks"]
    assert len(hooks["PostToolUse"]) == 1
    assert len(hooks["PostToolUse"][0]["hooks"]) == 1


def test_init_preserves_a_users_own_hook_on_the_same_event(tmp_path: Path, monkeypatch) -> None:
    """A user's own PreToolUse-style hook on an event Cartographer also uses
    must survive init — only Cartographer's own prior entries get evicted."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(json.dumps({
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own-linter"}]}]},
    }), encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    stop_commands = {h["command"] for group in _settings(tmp_path)["hooks"]["Stop"] for h in group["hooks"]}
    assert stop_commands == {"my-own-linter", "cartographer hook flush"}


def test_promote_is_noop_for_local_topology(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path)])
    result = runner.invoke(app, ["promote", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert "nothing to promote" in result.output


# ---------------------------------------------------------------------------
# Phase 5: topology=none (indexing opt-out)
# ---------------------------------------------------------------------------

def test_init_topology_none_skips_indexing_but_installs_packs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python", "--topology", "none"])
    assert result.exit_code == 0, result.output

    # No indexing artifacts at all
    assert not (tmp_path / ".cartographer" / "local").exists()
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".claude" / "skills" / "archaeology").exists()
    assert not (tmp_path / ".claude" / "skills" / "recall").exists()

    # Standards/skills/agents packs still install normally
    assert (tmp_path / ".claude" / "standards" / "python").is_dir()
    assert (tmp_path / ".claude" / "skills" / "accessibility" / "SKILL.md").exists()  # a core skill
    assert len(list((tmp_path / ".claude" / "agents").glob("*.md"))) > 0

    cfg = config_mod.load_config(tmp_path)
    assert cfg.topology.mode == "none"


def test_init_topology_none_claude_md_has_no_index_mandate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--topology", "none"])
    assert result.exit_code == 0, result.output

    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "VDB and KG are your primary search tools" not in claude_md
    assert "Standards live under" in claude_md


def test_init_topology_none_does_not_delete_existing_local_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert (tmp_path / ".cartographer" / "local" / "vdb.lance").exists()

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--topology", "none"])
    assert result.exit_code == 0, result.output

    # Switching to none doesn't delete what was already provisioned -- it just
    # stops maintaining it going forward.
    assert (tmp_path / ".cartographer" / "local" / "vdb.lance").exists()


def test_doctor_passes_with_topology_none_and_no_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    runner.invoke(app, ["init", "--path", str(tmp_path), "--topology", "none"])
    result = runner.invoke(app, ["doctor", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "indexing disabled" in result.output
    assert "all local checks passed" in result.output
