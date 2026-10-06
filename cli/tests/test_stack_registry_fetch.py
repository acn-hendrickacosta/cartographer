"""SR.2 integration: `cartographer stack add` / `init --stack` against a real
local HTTP server standing in for the web app's authenticated
GET /api/packs/:name/content/:content_type endpoint.

A real server (not a mocked urlopen) exercises the actual HTTP request --
headers, status codes, response body -- the way test_standards_registry.py's
unit tests don't. Covers all three content types (standards/skills/agents)
since apply_pack now fetches each independently for ("core", <stack name>).
"""

from __future__ import annotations

import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cartographer import config as config_mod
from cartographer.cli import app

runner = CliRunner()

VALID_TOKEN = "sk-valid-test-token"
PACK_VERSION = "9.9.9"


def _standards_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("guide.md", "# Registry-fetched guide\ndistinctive-marker-abc123\n")
    return buf.getvalue()


def _skills_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("registry-skill/SKILL.md", "# Registry-fetched skill\n")
    return buf.getvalue()


def _agents_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("registry-agent.md", "# Registry-fetched agent\n")
    return buf.getvalue()


_ZIPS_BY_TYPE = {"standards": _standards_zip(), "skills": _skills_zip(), "agents": _agents_zip()}


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {VALID_TOKEN}":
                self.send_response(401)
                self.end_headers()
                return
            # Expected shape: /api/packs/<name>/content/<type>
            parts = self.path.strip("/").split("/")
            if len(parts) != 5 or parts[:2] != ["api", "packs"] or parts[3] != "content":
                self.send_response(404)
                self.end_headers()
                return
            pack_name, content_type = parts[2], parts[4]
            if pack_name == "react" or content_type not in _ZIPS_BY_TYPE:
                # Simulates a pack/content-type with nothing published yet.
                self.send_response(404)
                self.end_headers()
                return
            zip_bytes = _ZIPS_BY_TYPE[content_type]
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("X-Pack-Version", PACK_VERSION)
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)

        def log_message(self, *args):
            pass  # keep test output quiet

    return Handler


@pytest.fixture
def registry_server():
    server = HTTPServer(("127.0.0.1", 0), _make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _configure_project(tmp_path: Path, registry_url: str, token: str, fallback: str = "warn") -> None:
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_test", name="test"),
        stacks=config_mod.StacksSection(
            active=["python"], registry_url=registry_url, registry_fallback=fallback
        ),
    )
    config_mod.save_config(tmp_path, cfg)
    config_mod.save_local_override(
        tmp_path, config_mod.LocalOverrideConfig(registry_token=token)
    )


def test_stack_add_fetches_all_content_types_from_registry_with_valid_token(tmp_path, registry_server):
    _configure_project(tmp_path, registry_server, VALID_TOKEN)

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    standards_content = (tmp_path / ".claude" / "standards" / "python" / "guide.md").read_text()
    assert "distinctive-marker-abc123" in standards_content
    # Skills/agents are fetched once each for "core" and "python" -- both write
    # to the same destination (the fake server returns the same content for
    # either pack name), so one copy landing is sufficient confirmation.
    assert (tmp_path / ".claude" / "skills" / "registry-skill" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "agents" / "registry-agent.md").exists()
    assert f"v{PACK_VERSION}" in result.output


def test_stack_add_invalid_token_falls_back_to_bundled_with_warn(tmp_path, registry_server):
    _configure_project(tmp_path, registry_server, "wrong-token", fallback="warn")

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "warning" in result.output.lower()
    standards_dest = tmp_path / ".claude" / "standards" / "python"
    # registry content never landed anywhere
    assert not (standards_dest / "guide.md").exists()
    assert not (tmp_path / ".claude" / "skills" / "registry-skill").exists()
    assert not (tmp_path / ".claude" / "agents" / "registry-agent.md").exists()
    # real bundled content did land for all three types
    assert (standards_dest / "testing.md").exists()
    assert len(list(standards_dest.glob("*.md"))) > 1
    assert (tmp_path / ".claude" / "skills").is_dir()
    assert (tmp_path / ".claude" / "agents").is_dir()


def test_stack_add_invalid_token_exits_nonzero_with_error_fallback(tmp_path, registry_server):
    _configure_project(tmp_path, registry_server, "wrong-token", fallback="error")

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 1


def test_stack_add_missing_token_falls_back_without_network_call(tmp_path, registry_server):
    _configure_project(tmp_path, registry_server, "", fallback="warn")

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "no registry_token" in " ".join(result.output.split())
    assert len(list((tmp_path / ".claude" / "standards" / "python").glob("*.md"))) > 1


def test_stack_add_unpublished_pack_falls_back_to_bundled_silently(tmp_path, registry_server):
    """react is a real KNOWN_PACKS name; the fake server 404s it specifically
    to simulate a pack with nothing published in the registry at all. A 404
    is always a silent fallback (no warning) -- it's the expected shape of
    the data (e.g. a pack with no stack-specific agents), not a failure."""
    _configure_project(tmp_path, registry_server, VALID_TOKEN, fallback="warn")

    result = runner.invoke(app, ["stack", "add", "react", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "warning" not in result.output.lower()
    assert len(list((tmp_path / ".claude" / "standards" / "react").glob("*.md"))) >= 1


def test_stack_add_no_registry_url_uses_bundled_without_network_call(tmp_path):
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_test", name="test"),
        stacks=config_mod.StacksSection(active=["python"]),
    )
    config_mod.save_config(tmp_path, cfg)

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert len(list((tmp_path / ".claude" / "standards" / "python").glob("*.md"))) > 1


def test_init_stack_fetches_from_registry_on_rerun_with_existing_config(tmp_path, registry_server, monkeypatch):
    from cartographer import registry as registry_mod
    monkeypatch.setattr(registry_mod, "registry_path", lambda: tmp_path / "registry-home" / "registry.json")

    # First init: no registry configured yet (fresh project), bundled only.
    first = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python"])
    assert first.exit_code == 0, first.output

    # Now configure the registry (simulating a team adopting it later) and re-run init --stacks.
    cfg = config_mod.load_config(tmp_path)
    cfg.stacks.registry_url = registry_server
    config_mod.save_config(tmp_path, cfg)
    config_mod.save_local_override(tmp_path, config_mod.LocalOverrideConfig(registry_token=VALID_TOKEN))

    second = runner.invoke(app, ["init", "--path", str(tmp_path), "--stacks", "python"])
    assert second.exit_code == 0, second.output

    content = (tmp_path / ".claude" / "standards" / "python" / "guide.md").read_text()
    assert "distinctive-marker-abc123" in content
