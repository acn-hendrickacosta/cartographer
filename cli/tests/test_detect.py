from pathlib import Path

from cartographer import claude_merge


def test_detect_reports_create_for_empty_workspace(tmp_path: Path) -> None:
    entries = claude_merge.detect(tmp_path)
    by_name = {e.name: e for e in entries}

    assert by_name["CLAUDE.md"].exists is False
    assert by_name["CLAUDE.md"].action == "create"
    assert by_name[".mcp.json"].action == "create"
    assert by_name[str(claude_merge.SETTINGS_JSON_REL)].action == "create"


def test_detect_reports_merge_for_existing_claude_md_without_marker(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# existing project notes\n", encoding="utf-8")

    entries = claude_merge.detect(tmp_path)
    claude_md_entry = next(e for e in entries if e.name == "CLAUDE.md")

    assert claude_md_entry.exists is True
    assert claude_md_entry.action == "merge"


def test_detect_reports_unchanged_when_marker_already_present(tmp_path: Path) -> None:
    claude_merge.ensure_claude_md(tmp_path)

    entries = claude_merge.detect(tmp_path)
    claude_md_entry = next(e for e in entries if e.name == "CLAUDE.md")

    assert claude_md_entry.action == "unchanged"
