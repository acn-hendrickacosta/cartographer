import json
from pathlib import Path

from cartographer import claude_merge


def test_ensure_claude_md_creates_when_absent(tmp_path: Path) -> None:
    path, changed = claude_merge.ensure_claude_md(tmp_path)
    assert changed is True
    assert claude_merge.BEGIN_MARKER in path.read_text(encoding="utf-8")


def test_ensure_claude_md_is_idempotent(tmp_path: Path) -> None:
    claude_merge.ensure_claude_md(tmp_path)
    _, changed_again = claude_merge.ensure_claude_md(tmp_path)
    assert changed_again is False


def test_ensure_claude_md_backs_up_and_appends_to_existing_file(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# existing notes\n\nDo not break the build.\n", encoding="utf-8")

    path, changed = claude_merge.ensure_claude_md(tmp_path)

    assert changed is True
    text = path.read_text(encoding="utf-8")
    assert "Do not break the build." in text
    assert claude_merge.BEGIN_MARKER in text

    backups = list((tmp_path / claude_merge.BACKUP_DIR_REL).glob("CLAUDE.md.*.bak"))
    assert len(backups) == 1
    assert "Do not break the build." in backups[0].read_text(encoding="utf-8")


def test_deep_merge_settings_concatenates_and_dedupes_lists() -> None:
    existing = {"permissions": {"allow": ["Read", "Grep"]}}
    additions = {"permissions": {"allow": ["Grep", "Bash"]}}
    merged = claude_merge.deep_merge_settings(existing, additions)
    assert merged["permissions"]["allow"] == ["Read", "Grep", "Bash"]


def test_merge_mcp_servers_dedupes_by_name() -> None:
    existing = {"mcpServers": {"github": {"command": "gh-mcp"}}}
    additions = {"mcpServers": {"github": {"command": "gh-mcp-v2"}, "cartographer": {"command": "ct-mcp"}}}
    merged = claude_merge.merge_mcp_servers(existing, additions)
    assert merged["mcpServers"]["github"]["command"] == "gh-mcp-v2"
    assert merged["mcpServers"]["cartographer"]["command"] == "ct-mcp"


def test_ensure_mcp_json_no_op_when_no_additions_and_file_exists(tmp_path: Path) -> None:
    mcp_path = tmp_path / claude_merge.MCP_JSON_NAME
    mcp_path.write_text(json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}), encoding="utf-8")

    path, changed = claude_merge.ensure_mcp_json(tmp_path, additions=None)

    assert changed is False
    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["github"]["command"] == "gh-mcp"


def test_ensure_settings_json_no_op_when_absent_and_no_additions(tmp_path: Path) -> None:
    path, changed = claude_merge.ensure_settings_json(tmp_path, additions=None)
    assert changed is False
    assert not path.exists()
