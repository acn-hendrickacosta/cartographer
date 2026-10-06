"""SR.5 integration: `cartographer stack fork` / `stack push`, and the
pack_provenance.json manifest apply_pack maintains to make push possible for
skills/agents (which live in a directory shared across packs, unlike
standards which are already pack-isolated).

Uses a real local HTTP server (same pattern as test_stack_registry_fetch.py)
standing in for the web app's POST .../fork and PUT .../fork/:content_type
routes, with server-side state (forked_packs, pushed) tracked on the server
instance so a single test can simulate a multi-request sequence (fork, then
push, then check what was pushed).
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cartographer import config as config_mod
from cartographer.cli import app
from cartographer.commands.stack import PROVENANCE_REL

runner = CliRunner()

VALID_TOKEN = "sk-valid-test-token"


def _make_fork_handler():
    class Handler(BaseHTTPRequestHandler):
        def _authed(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {VALID_TOKEN}"

        def do_GET(self):
            # Not exercised by these tests -- fork/push don't depend on fetch
            # succeeding. Blanket 404 so stack add's registry attempt falls
            # back to bundled content (which is what gets pushed).
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            if not self._authed():
                self.send_response(401)
                self.end_headers()
                return
            parts = self.path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "packs"] or parts[3] != "fork":
                self.send_response(404)
                self.end_headers()
                return
            pack_name = parts[2]
            if pack_name == "nope":
                self.send_response(404)
                self.end_headers()
                return
            if pack_name in self.server.forked_packs:  # type: ignore[attr-defined]
                self.send_response(409)
                self.end_headers()
                return
            self.server.forked_packs.add(pack_name)  # type: ignore[attr-defined]
            body = json.dumps({"pack": pack_name, "version": "fork", "forked_from": "1.0.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            if not self._authed():
                self.send_response(401)
                self.end_headers()
                return
            parts = self.path.strip("/").split("/")
            if len(parts) != 5 or parts[:2] != ["api", "packs"] or parts[3] != "fork":
                self.send_response(404)
                self.end_headers()
                return
            pack_name, content_type = parts[2], parts[4]
            if pack_name not in self.server.forked_packs:  # type: ignore[attr-defined]
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            self.server.pushed.setdefault(pack_name, {})[content_type] = body  # type: ignore[attr-defined]
            resp = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        def log_message(self, *args):
            pass  # keep test output quiet

    return Handler


@pytest.fixture
def fork_server():
    server = HTTPServer(("127.0.0.1", 0), _make_fork_handler())
    server.forked_packs = set()
    server.pushed = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _configure_project(tmp_path: Path, registry_url: str, token: str = VALID_TOKEN) -> None:
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_test", name="test"),
        stacks=config_mod.StacksSection(active=["python"], registry_url=registry_url, registry_fallback="warn"),
    )
    config_mod.save_config(tmp_path, cfg)
    config_mod.save_local_override(tmp_path, config_mod.LocalOverrideConfig(registry_token=token))


def test_stack_fork_success(tmp_path, fork_server):
    server, registry_url = fork_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "fork", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "forked 'python'" in result.output
    assert "python" in server.forked_packs


def test_stack_fork_already_forked_returns_nonzero(tmp_path, fork_server):
    server, registry_url = fork_server
    server.forked_packs.add("python")
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "fork", "python", "--path", str(tmp_path)])

    assert result.exit_code == 1


def test_stack_fork_unpublished_pack_returns_nonzero(tmp_path, fork_server):
    _, registry_url = fork_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "fork", "nope", "--path", str(tmp_path)])

    assert result.exit_code == 1


def test_stack_add_writes_provenance_manifest(tmp_path, fork_server):
    _, registry_url = fork_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / PROVENANCE_REL).read_text())
    assert manifest["standards"]["python"]  # non-empty: bundled guide.md etc landed
    assert "core" in manifest["skills"]
    assert "python" in manifest["skills"]
    assert "core" in manifest["agents"]
    assert "python" in manifest["agents"]
    # Matches what's actually on disk
    standards_dir = tmp_path / ".claude" / "standards" / "python"
    assert set(manifest["standards"]["python"]) == {p.name for p in standards_dir.glob("*.md")}


def test_stack_push_without_fork_returns_nonzero(tmp_path, fork_server):
    _, registry_url = fork_server
    _configure_project(tmp_path, registry_url)
    runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])

    result = runner.invoke(app, ["stack", "push", "python", "--path", str(tmp_path)])

    assert result.exit_code == 1


def test_stack_push_after_fork_sends_current_local_content(tmp_path, fork_server):
    server, registry_url = fork_server
    _configure_project(tmp_path, registry_url)
    runner.invoke(app, ["stack", "add", "python", "--path", str(tmp_path)])
    runner.invoke(app, ["stack", "fork", "python", "--path", str(tmp_path)])

    # Simulate a local customization before pushing.
    standards_dir = tmp_path / ".claude" / "standards" / "python"
    testing_md = standards_dir / "testing.md"
    testing_md.write_text(testing_md.read_text() + "\nlocal-customization-marker\n")

    result = runner.invoke(app, ["stack", "push", "python", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "python" in server.pushed
    standards_zip = server.pushed["python"]["standards"]
    with zipfile.ZipFile(io.BytesIO(standards_zip)) as zf:
        assert "local-customization-marker" in zf.read("testing.md").decode()
    # Skills/agents were also pushed (core + python both have bundled content)
    assert "skills" in server.pushed["python"]
    assert "agents" in server.pushed["python"]
    with zipfile.ZipFile(io.BytesIO(server.pushed["python"]["skills"])) as zf:
        names = zf.namelist()
    assert any(name.endswith("SKILL.md") for name in names)


def test_stack_push_no_installed_content_is_a_noop(tmp_path, fork_server):
    server, registry_url = fork_server
    _configure_project(tmp_path, registry_url)
    # Fork a pack that was never `stack add`-ed locally, so the provenance
    # manifest has nothing for it.
    server.forked_packs.add("typescript")

    result = runner.invoke(app, ["stack", "push", "typescript", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "nothing to push" in result.output
    assert "typescript" not in server.pushed
