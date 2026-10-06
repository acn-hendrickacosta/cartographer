"""Publish reassembly logic (app/publish.py), against mocked s3_registry."""

from __future__ import annotations

from unittest.mock import patch

from app import publish, s3_registry


def _draft(**overrides):
    base = {
        "id": "draft-1",
        "pack_name": "python",
        "content_type": "standards",
        "file_name": "testing.md",
        "target_version": "2.0.0",
        "author_email": "author@example.com",
        "content": "# new testing content",
        "state": "APPROVED",
    }
    base.update(overrides)
    return base


def test_publish_merges_drafted_file_with_existing_standards_files():
    draft = _draft()
    with patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=b"existing-zip-bytes"), \
         patch.object(s3_registry, "list_files_in_zip", return_value={"testing.md": "old content", "patterns.md": "unchanged"}), \
         patch.object(s3_registry, "build_zip_from_files") as mock_build, \
         patch.object(s3_registry, "put_content_zip") as mock_put_zip, \
         patch.object(s3_registry, "put_version_metadata") as mock_put_meta, \
         patch.object(s3_registry, "put_latest") as mock_put_latest:
        mock_build.return_value = b"new-zip-bytes"
        publish.publish_draft(draft)

    merged_files = mock_build.call_args[0][0]
    assert merged_files == {"testing.md": "# new testing content", "patterns.md": "unchanged"}
    mock_put_zip.assert_called_once_with("python", "2.0.0", "standards", b"new-zip-bytes")
    mock_put_latest.assert_called_once_with("python", "2.0.0")
    metadata = mock_put_meta.call_args[0][2]
    assert metadata["published_by"] == "author@example.com"
    assert metadata["version"] == "2.0.0"


def test_publish_skills_preserves_skill_name_keys():
    draft = _draft(content_type="skills", file_name="new-skill/SKILL.md", content="# new skill")
    with patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=b"existing-zip-bytes"), \
         patch.object(s3_registry, "list_skills_in_zip", return_value={"existing-skill": {"SKILL.md": "old"}}), \
         patch.object(s3_registry, "build_zip_from_files") as mock_build, \
         patch.object(s3_registry, "put_content_zip"), \
         patch.object(s3_registry, "put_version_metadata"), \
         patch.object(s3_registry, "put_latest"):
        mock_build.return_value = b"zip"
        publish.publish_draft(draft)

    merged_files = mock_build.call_args[0][0]
    assert merged_files == {"existing-skill/SKILL.md": "old", "new-skill/SKILL.md": "# new skill"}


def test_publish_first_ever_version_has_no_existing_files():
    """A pack with nothing published yet (e.g. a brand new pack, or 'core'
    getting its first standards content) -- get_latest returns None, so the
    draft's file is the only one in the new archive."""
    draft = _draft(pack_name="core", target_version="1.0.0")
    with patch.object(s3_registry, "get_latest", return_value=None), \
         patch.object(s3_registry, "build_zip_from_files") as mock_build, \
         patch.object(s3_registry, "put_content_zip"), \
         patch.object(s3_registry, "put_version_metadata"), \
         patch.object(s3_registry, "put_latest"):
        mock_build.return_value = b"zip"
        publish.publish_draft(draft)

    merged_files = mock_build.call_args[0][0]
    assert merged_files == {"testing.md": "# new testing content"}
