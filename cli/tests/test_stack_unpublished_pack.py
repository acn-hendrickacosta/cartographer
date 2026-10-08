"""SR.5 gap 2: forking/consuming a pack that was never published as a global
baseline at all -- an enterprise-exclusive standard/harness meant to exist
only inside one tenant's own fork. See docs/phases/sr-5-project-forks.md's
"Closing gap 2" section.

Uses a real local HTTP server (same pattern as test_stack_registry_fetch.py /
test_stack_fork_push.py) that additionally models the real server's actual
fork-then-serve round trip (GET returns whatever was last PUT for a pack), so
these tests can prove the full cross-project scenario: one workspace forks
and pushes content with no prior baseline, and a second, completely separate
workspace pulls it back via a plain `stack add` -- not just that the
originating workspace can see its own fork.
"""

from __future__ import annotations

import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cartographer import config as config_mod
from cartographer.cli import app
from cartographer.commands.stack import PROVENANCE_REL

runner = CliRunner()

VALID_TOKEN = "sk-gap2-test-token"


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def _authed(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {VALID_TOKEN}"

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authed():
                self.send_response(401)
                self.end_headers()
                return
            parts = self.path.strip("/").split("/")
            if len(parts) != 5 or parts[:2] != ["api", "packs"] or parts[3] != "content":
                self.send_response(404)
                self.end_headers()
                return
            pack_name, content_type = parts[2], parts[4]
            content = self.server.fork_content.get(pack_name, {}).get(content_type)  # type: ignore[attr-defined]
            if content is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("X-Pack-Version", "fork")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

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
            if pack_name in self.server.forked_packs:  # type: ignore[attr-defined]
                self.send_response(409)
                self.end_headers()
                return
            if pack_name not in self.server.registered_packs:  # type: ignore[attr-defined]
                self.send_response(404)
                self.end_headers()
                return
            self.server.forked_packs.add(pack_name)  # type: ignore[attr-defined]
            self._send_json(200, {"pack": pack_name, "version": "fork", "forked_from": None})

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
            self.server.fork_content.setdefault(pack_name, {})[content_type] = body  # type: ignore[attr-defined]
            self._send_json(200, {"ok": True})

        def log_message(self, *args):
            pass  # keep test output quiet

    return Handler


@pytest.fixture
def gap2_server():
    server = HTTPServer(("127.0.0.1", 0), _make_handler())
    server.registered_packs = {"acme-harness"}  # simulates the packs_admin Postgres table
    server.forked_packs = set()
    server.fork_content = {}
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
        stacks=config_mod.StacksSection(active=[], registry_url=registry_url, registry_fallback="warn"),
    )
    config_mod.save_config(tmp_path, cfg)
    config_mod.save_local_override(tmp_path, config_mod.LocalOverrideConfig(registry_token=token))


def test_stack_fork_unregistered_pack_returns_nonzero(tmp_path, gap2_server):
    _, registry_url = gap2_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "fork", "totally-unregistered", "--path", str(tmp_path)])

    assert result.exit_code == 1


def test_stack_fork_registered_but_unpublished_creates_empty_fork(tmp_path, gap2_server):
    server, registry_url = gap2_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "fork", "acme-harness", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "new, empty fork" in result.output
    assert "acme-harness" in server.forked_packs
    assert (tmp_path / ".claude" / "standards" / "acme-harness").is_dir()


def test_apply_pack_still_rejects_unknown_pack_without_registry(tmp_path):
    """Regression: a project that hasn't configured a registry at all keeps
    today's typo protection exactly as before."""
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_test", name="test"),
        stacks=config_mod.StacksSection(active=[]),
    )
    config_mod.save_config(tmp_path, cfg)

    result = runner.invoke(app, ["stack", "add", "totally-made-up-name", "--path", str(tmp_path)])

    assert result.exit_code != 0


def test_apply_pack_accepts_unbundled_pack_when_registry_configured(tmp_path, gap2_server):
    """A registry-only pack name isn't rejected just for being unbundled --
    it's attempted via fetch like any other pack. With nothing published or
    forked yet, this is a content-free no-op with a visible warning, not a
    crash."""
    _, registry_url = gap2_server
    _configure_project(tmp_path, registry_url)

    result = runner.invoke(app, ["stack", "add", "acme-harness", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "has no content of any kind" in result.output


def test_stack_push_standards_works_without_prior_stack_add(tmp_path, gap2_server):
    server, registry_url = gap2_server
    _configure_project(tmp_path, registry_url)
    runner.invoke(app, ["stack", "fork", "acme-harness", "--path", str(tmp_path)])

    # Hand-author the file directly -- stack add is never run for this pack.
    standards_dir = tmp_path / ".claude" / "standards" / "acme-harness"
    standards_dir.mkdir(parents=True, exist_ok=True)
    (standards_dir / "guide.md").write_text("# Acme harness guide\n")

    result = runner.invoke(app, ["stack", "push", "acme-harness", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "acme-harness" in server.fork_content
    with zipfile.ZipFile(BytesIO(server.fork_content["acme-harness"]["standards"])) as zf:
        assert zf.read("guide.md").decode() == "# Acme harness guide\n"


def test_stack_adopt_rejects_standards_content_type(tmp_path):
    result = runner.invoke(app, ["stack", "adopt", "acme-harness", "standards", "guide", "--path", str(tmp_path)])
    assert result.exit_code == 1


def test_stack_adopt_fails_for_nonexistent_skill_file(tmp_path):
    result = runner.invoke(app, ["stack", "adopt", "acme-harness", "skills", "does-not-exist", "--path", str(tmp_path)])
    assert result.exit_code == 1


def test_stack_adopt_then_push_includes_skills_and_agents(tmp_path, gap2_server):
    server, registry_url = gap2_server
    _configure_project(tmp_path, registry_url)
    runner.invoke(app, ["stack", "fork", "acme-harness", "--path", str(tmp_path)])

    # Hand-author a skill and an agent -- neither ever went through apply_pack.
    skill_dir = tmp_path / ".claude" / "skills" / "acme-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Acme review skill\n")

    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "acme-compliance-reviewer.md").write_text("# Acme compliance reviewer\n")

    adopt_skill = runner.invoke(app, ["stack", "adopt", "acme-harness", "skills", "acme-review", "--path", str(tmp_path)])
    assert adopt_skill.exit_code == 0, adopt_skill.output
    adopt_agent = runner.invoke(
        app, ["stack", "adopt", "acme-harness", "agents", "acme-compliance-reviewer", "--path", str(tmp_path)]
    )
    assert adopt_agent.exit_code == 0, adopt_agent.output

    manifest = json.loads((tmp_path / PROVENANCE_REL).read_text())
    assert manifest["skills"]["acme-harness"] == ["acme-review"]
    assert manifest["agents"]["acme-harness"] == ["acme-compliance-reviewer.md"]

    result = runner.invoke(app, ["stack", "push", "acme-harness", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output

    with zipfile.ZipFile(BytesIO(server.fork_content["acme-harness"]["skills"])) as zf:
        assert zf.read("acme-review/SKILL.md").decode() == "# Acme review skill\n"
    with zipfile.ZipFile(BytesIO(server.fork_content["acme-harness"]["agents"])) as zf:
        assert zf.read("acme-compliance-reviewer.md").decode() == "# Acme compliance reviewer\n"


def test_second_workspace_pulls_first_workspaces_pushed_pack_via_stack_add(tmp_path_factory, gap2_server):
    """The actual point of closing gap 2: a project that never forked
    anything itself can still transparently pull another project's pushed,
    registry-only pack via a plain `stack add` -- proving this isn't limited
    to the originating workspace."""
    server, registry_url = gap2_server
    workspace_a = tmp_path_factory.mktemp("workspace-a")
    workspace_b = tmp_path_factory.mktemp("workspace-b")

    _configure_project(workspace_a, registry_url)
    runner.invoke(app, ["stack", "fork", "acme-harness", "--path", str(workspace_a)])
    (workspace_a / ".claude" / "standards" / "acme-harness").mkdir(parents=True, exist_ok=True)
    (workspace_a / ".claude" / "standards" / "acme-harness" / "guide.md").write_text("# Shared Acme guide\n")
    push_result = runner.invoke(app, ["stack", "push", "acme-harness", "--path", str(workspace_a)])
    assert push_result.exit_code == 0, push_result.output

    # workspace_b never forked or pushed anything -- it's a completely
    # separate, unrelated project directory.
    _configure_project(workspace_b, registry_url)
    add_result = runner.invoke(app, ["stack", "add", "acme-harness", "--path", str(workspace_b)])

    assert add_result.exit_code == 0, add_result.output
    content = (workspace_b / ".claude" / "standards" / "acme-harness" / "guide.md").read_text()
    assert content == "# Shared Acme guide\n"
