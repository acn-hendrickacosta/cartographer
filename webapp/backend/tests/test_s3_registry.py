"""S3 registry reads (app/s3_registry.py), against a mocked boto3 S3 client."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from app import s3_registry


def _not_found_error(operation: str) -> ClientError:
    return ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, operation)


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_list_packs_returns_sorted_names():
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"CommonPrefixes": [{"Prefix": "packs/react/"}, {"Prefix": "packs/python/"}]}
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.list_packs()
    assert result == ["python", "react"]


def test_get_latest_returns_parsed_json():
    mock_s3 = MagicMock()
    body = MagicMock()
    body.read.return_value = json.dumps({"pack": "python", "version": "1.0.0"}).encode()
    mock_s3.get_object.return_value = {"Body": body}
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.get_latest("python")
    assert result == {"pack": "python", "version": "1.0.0"}
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="packs/python/latest.json")


def test_get_latest_missing_pack_returns_none():
    mock_s3 = MagicMock()
    mock_s3.get_object.side_effect = _not_found_error("GetObject")
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.get_latest("nonexistent")
    assert result is None


def test_list_versions_sorted():
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"CommonPrefixes": [{"Prefix": "packs/python/2.0.0/"}, {"Prefix": "packs/python/1.0.0/"}]}
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.list_versions("python")
    assert result == ["1.0.0", "2.0.0"]


def test_list_files_in_zip_decodes_all_md_files():
    zb = _zip_bytes({"guide.md": "# Guide", "testing.md": "# Testing"})
    result = s3_registry.list_files_in_zip(zb)
    assert result == {"guide.md": "# Guide", "testing.md": "# Testing"}


def test_get_content_zip_missing_version_returns_none():
    mock_s3 = MagicMock()
    mock_s3.get_object.side_effect = _not_found_error("GetObject")
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.get_content_zip("python", "9.9.9", "standards")
    assert result is None


def test_get_content_zip_uses_content_type_in_key():
    mock_s3 = MagicMock()
    body = MagicMock()
    body.read.return_value = b"zip-bytes"
    mock_s3.get_object.return_value = {"Body": body}
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.get_content_zip("python", "1.0.0", "skills")
    assert result == b"zip-bytes"
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="packs/python/1.0.0/skills.zip")


def test_available_content_types_probes_each_type():
    def fake_head_object(Bucket, Key):
        if Key.endswith("agents.zip"):
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    mock_s3 = MagicMock()
    mock_s3.head_object.side_effect = fake_head_object
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.available_content_types("angular", "1.0.0")
    assert result == ["standards", "skills"]


def test_list_registry_index_parses_zips_and_bare_pack_prefixes():
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "packs/python/1.0.0/standards.zip"},
                {"Key": "packs/python/1.0.0/skills.zip"},
                {"Key": "packs/python/1.0.0/version.json"},
                {"Key": "packs/python/latest.json"},
                {"Key": "packs/core/1.0.0/agents.zip"},
            ]
        }
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    with patch.object(s3_registry, "_s3", mock_s3):
        index = s3_registry.list_registry_index()
    assert index["python"]["1.0.0"] == {"standards", "skills"}
    assert index["core"]["1.0.0"] == {"agents"}


def test_get_latest_many_dispatches_concurrently_and_preserves_names():
    with patch.object(s3_registry, "get_latest", side_effect=lambda name: {"version": f"v-{name}"}):
        result = s3_registry.get_latest_many(["python", "core", "angular"])
    assert result == {
        "python": {"version": "v-python"},
        "core": {"version": "v-core"},
        "angular": {"version": "v-angular"},
    }


def test_list_skills_in_zip_groups_by_skill_name():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("archaeology/SKILL.md", "# Archaeology")
        zf.writestr("recall/SKILL.md", "# Recall")

    result = s3_registry.list_skills_in_zip(buf.getvalue())

    assert result == {
        "archaeology": {"SKILL.md": "# Archaeology"},
        "recall": {"SKILL.md": "# Recall"},
    }


# ---------------------------------------------------------------------------
# SR.5: per-project forks
# ---------------------------------------------------------------------------

def test_get_latest_with_project_id_uses_project_prefix():
    mock_s3 = MagicMock()
    body = MagicMock()
    body.read.return_value = json.dumps({"pack": "python", "version": "fork"}).encode()
    mock_s3.get_object.return_value = {"Body": body}
    with patch.object(s3_registry, "_s3", mock_s3):
        result = s3_registry.get_latest("python", project_id="proj_x")
    assert result == {"pack": "python", "version": "fork"}
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="projects/proj_x/packs/python/latest.json")


def test_project_has_fork_true_when_fork_latest_exists():
    with patch.object(s3_registry, "get_latest", return_value={"pack": "python", "version": "fork"}):
        assert s3_registry.project_has_fork("python", "proj_x") is True


def test_project_has_fork_false_when_no_fork_latest():
    with patch.object(s3_registry, "get_latest", return_value=None):
        assert s3_registry.project_has_fork("python", "proj_x") is False


def test_fork_pack_for_project_creates_empty_fork_when_no_baseline():
    """An enterprise-exclusive pack with no global baseline at all still
    forks successfully -- just with nothing copied and forked_from: None.
    Whether an unpublished name is *legitimate* to fork is the caller's
    (main.py's) decision via packs_admin.pack_exists, not this function's."""
    with patch.object(s3_registry, "get_latest", return_value=None), \
         patch.object(s3_registry, "put_content_zip") as mock_put_content, \
         patch.object(s3_registry, "put_latest") as mock_put_latest:
        result = s3_registry.fork_pack_for_project("acme-harness", "proj_x")

    mock_put_content.assert_not_called()
    mock_put_latest.assert_called_once_with("acme-harness", s3_registry.FORK_VERSION, project_id="proj_x")
    assert result == {"pack": "acme-harness", "version": s3_registry.FORK_VERSION, "forked_from": None}


def test_fork_pack_for_project_copies_only_existing_content_types():
    def fake_get_latest(pack_name, project_id=None):
        assert project_id is None
        return {"pack": "core", "version": "1.0.0"}

    def fake_get_content_zip(pack_name, version, content_type):
        # "core" has only skills+agents, no standards -- mirrors the real bucket
        return None if content_type == "standards" else f"{content_type}-bytes".encode()

    put_calls = []

    def fake_put_content_zip(pack_name, version, content_type, zip_bytes, project_id=None):
        put_calls.append((pack_name, version, content_type, zip_bytes, project_id))

    with patch.object(s3_registry, "get_latest", side_effect=fake_get_latest), \
         patch.object(s3_registry, "get_content_zip", side_effect=fake_get_content_zip), \
         patch.object(s3_registry, "put_content_zip", side_effect=fake_put_content_zip), \
         patch.object(s3_registry, "put_latest") as mock_put_latest:
        result = s3_registry.fork_pack_for_project("core", "proj_x")

    assert {c[2] for c in put_calls} == {"skills", "agents"}
    assert all(c[1] == s3_registry.FORK_VERSION and c[4] == "proj_x" for c in put_calls)
    mock_put_latest.assert_called_once_with("core", s3_registry.FORK_VERSION, project_id="proj_x")
    assert result == {"pack": "core", "version": s3_registry.FORK_VERSION, "forked_from": "1.0.0"}
