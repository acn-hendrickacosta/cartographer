import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cartographer import config as config_mod, registry
from cartographer.cli import app
from cartographer.indexing import kg
from cartographer.runtime import serve_state

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


# ---------------------------------------------------------------------------
# --registry-url / --registry-token on `init` (lets a brand-new init fetch
# from the registry on its very first run, instead of requiring a manual
# config edit + a second run)
# ---------------------------------------------------------------------------

VALID_TOKEN = "sk-init-flag-test-token"
PACK_VERSION = "9.9.9"


def _registry_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("guide.md", "# From the registry\ninit-flag-marker\n")
    return buf.getvalue()


def _make_init_flag_handler():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Authorization", "") != f"Bearer {VALID_TOKEN}":
                self.send_response(401)
                self.end_headers()
                return
            parts = self.path.strip("/").split("/")
            if len(parts) != 5 or parts[:2] != ["api", "packs"] or parts[3] != "content":
                self.send_response(404)
                self.end_headers()
                return
            content_type = parts[4]
            if content_type != "standards":
                self.send_response(404)
                self.end_headers()
                return
            body = _registry_zip()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("X-Pack-Version", PACK_VERSION)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


@pytest.fixture
def init_flag_server():
    server = HTTPServer(("127.0.0.1", 0), _make_init_flag_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def test_init_registry_flags_fetch_on_first_run(tmp_path: Path, monkeypatch, init_flag_server) -> None:
    """Regression guard for the previous behavior: a brand-new init used to be
    unable to use the registry at all (config didn't exist yet when apply_pack
    ran), requiring a manual config edit plus a second run. --registry-url/
    --registry-token must make the very first run fetch."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, [
        "init", "--path", str(tmp_path), "--stacks", "python",
        "--registry-url", init_flag_server, "--registry-token", VALID_TOKEN,
    ])

    assert result.exit_code == 0, result.output
    assert f"v{PACK_VERSION}" in result.output
    content = (tmp_path / ".claude" / "standards" / "python" / "guide.md").read_text()
    assert "init-flag-marker" in content

    cfg = config_mod.load_config(tmp_path)
    assert cfg.stacks.registry_url == init_flag_server
    override = config_mod.load_local_override(tmp_path)
    assert override.registry_token == VALID_TOKEN


def test_init_registry_token_without_url_warns_and_skips_fetch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--registry-token", VALID_TOKEN])

    assert result.exit_code == 0, result.output
    assert "no registry_url configured" in result.output
    override = config_mod.load_local_override(tmp_path)
    assert override.registry_token == VALID_TOKEN  # still saved for later use


def test_init_registry_token_rerun_updates_existing_local_override(tmp_path: Path, monkeypatch, init_flag_server) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    first = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert first.exit_code == 0, first.output
    assert config_mod.load_local_override(tmp_path).registry_token == ""

    second = runner.invoke(app, [
        "init", "--path", str(tmp_path),
        "--registry-url", init_flag_server, "--registry-token", VALID_TOKEN,
    ])
    assert second.exit_code == 0, second.output
    assert config_mod.load_local_override(tmp_path).registry_token == VALID_TOKEN
    assert config_mod.load_config(tmp_path).stacks.registry_url == init_flag_server


# ---------------------------------------------------------------------------
# KG single-writer lock conflict with a running `cartographer serve` (found
# live: re-running `init` on a workspace serve already watches crashed with a
# raw Kuzu "Could not set lock on file" RuntimeError -- see kg.py's _connect
# docstring for why a second process can never open the KG read-write while
# serve holds it. Expected and healthy, not a real failure, as long as serve
# really is the one holding the lock.
# ---------------------------------------------------------------------------

_FAKE_SERVE_STATE = serve_state.ServeState(
    pid=1, vdb_pid=1, kg_pid=1, vdb_port=1, kg_port=1, started_at="2026-01-01T00:00:00Z"
)


def test_init_skips_kg_schema_check_gracefully_when_serve_holds_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    with patch.object(kg, "ensure_namespace", side_effect=RuntimeError("IO exception: Could not set lock on file")), \
         patch.object(serve_state, "current_running_state", return_value=_FAKE_SERVE_STATE):
        result = runner.invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.split())
    assert "KG schema check skipped" in normalized
    assert "already running" in normalized


def test_init_reraises_kg_lock_error_when_serve_not_running(tmp_path: Path, monkeypatch) -> None:
    """Regression: if the lock conflict can't be attributed to a running
    serve, it's a genuine problem (stale lock file, disk issue, ...) and must
    still surface, not be silently swallowed."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    with patch.object(kg, "ensure_namespace", side_effect=RuntimeError("IO exception: Could not set lock on file")), \
         patch.object(serve_state, "current_running_state", return_value=None):
        result = runner.invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code != 0


def test_doctor_reports_ok_when_serve_holds_kg_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    with patch.object(kg, "is_readable", return_value=False), \
         patch.object(serve_state, "current_running_state", return_value=_FAKE_SERVE_STATE), \
         patch.object(serve_state, "check_health", return_value={"watch": True}):
        result = runner.invoke(app, ["doctor", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.split())
    assert "write-locked, as expected" in normalized
    assert "all local checks passed" in normalized


def test_doctor_still_fails_when_kg_unreadable_and_serve_not_running(tmp_path: Path, monkeypatch) -> None:
    """Regression: a real KG problem with no serve process to explain it away
    must still fail doctor, exactly as before this fix."""
    monkeypatch.setattr(registry, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    with patch.object(kg, "is_readable", return_value=False), \
         patch.object(serve_state, "current_running_state", return_value=None):
        result = runner.invoke(app, ["doctor", "--path", str(tmp_path)])

    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "local KG not readable" in result.output
