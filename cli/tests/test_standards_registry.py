"""Standards Registry client (SR.2, extended to skills/agents): fetch_pack_content,
extract_pack_zip, and extract_skills_zip.

urllib.request.urlopen is monkeypatched with a fake response rather than
hitting a real HTTP server -- keeps these fast and deterministic. The
integration test (test_stack_registry_fetch.py) exercises the real HTTP path,
including auth header handling, against a local server instead.
"""

from __future__ import annotations

import io
import urllib.error
import zipfile
from unittest.mock import patch

import pytest

from cartographer.standards_registry import (
    RegistryContentNotFoundError,
    RegistryFetchError,
    extract_pack_zip,
    extract_skills_zip,
    fetch_pack_content,
)


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes, version: str = "1.0.0"):
        self._data = data
        self.headers = {"X-Pack-Version": version} if version else {}

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# fetch_pack_content
# ---------------------------------------------------------------------------

def test_fetch_pack_content_success():
    zip_bytes = _zip_bytes({"guide.md": "# Python standards"})
    captured_requests = []

    def fake_urlopen(request, timeout=None):
        captured_requests.append(request)
        return _FakeResponse(zip_bytes, version="1.2.0")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        version, content = fetch_pack_content("https://standards.example.com", "python", "standards", "sk-test-token")

    assert version == "1.2.0"
    assert content == zip_bytes
    assert captured_requests[0].full_url == "https://standards.example.com/api/packs/python/content/standards"
    assert captured_requests[0].headers["Authorization"] == "Bearer sk-test-token"


def test_fetch_pack_content_url_includes_content_type():
    captured_requests = []

    def fake_urlopen(request, timeout=None):
        captured_requests.append(request)
        return _FakeResponse(b"PK\x05\x06" + b"\x00" * 18, version="1.0.0")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        fetch_pack_content("https://standards.example.com/", "core", "skills", "sk-test-token")

    assert captured_requests[0].full_url == "https://standards.example.com/api/packs/core/content/skills"


def test_fetch_pack_content_missing_token_raises_without_network_call():
    with patch("urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(RegistryFetchError, match="no registry_token"):
            fetch_pack_content("https://standards.example.com", "python", "standards", "")
    mock_urlopen.assert_not_called()


def test_fetch_pack_content_401_raises_registry_fetch_error():
    error = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(RegistryFetchError, match="rejected the configured token"):
            fetch_pack_content("https://standards.example.com", "python", "standards", "bad-token")


def test_fetch_pack_content_404_raises_content_not_found_error():
    error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(RegistryContentNotFoundError, match="no published agents"):
            fetch_pack_content("https://standards.example.com", "angular", "agents", "sk-test-token")


def test_fetch_pack_content_404_is_also_a_registry_fetch_error():
    """RegistryContentNotFoundError is a RegistryFetchError subclass -- callers
    that only catch the base class still see it."""
    error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(RegistryFetchError):
            fetch_pack_content("https://standards.example.com", "angular", "agents", "sk-test-token")


def test_fetch_pack_content_network_error_raises():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        with pytest.raises(RegistryFetchError, match="could not reach"):
            fetch_pack_content("https://unreachable.example.com", "python", "standards", "sk-test-token")


def test_fetch_pack_content_missing_version_header_raises():
    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"PK\x05\x06" + b"\x00" * 18, version="")):
        with pytest.raises(RegistryFetchError, match="X-Pack-Version"):
            fetch_pack_content("https://standards.example.com", "python", "standards", "sk-test-token")


# ---------------------------------------------------------------------------
# extract_pack_zip (standards, agents -- flat)
# ---------------------------------------------------------------------------

def test_extract_pack_zip_writes_files_flat(tmp_path):
    zb = _zip_bytes({"guide.md": "# Guide", "testing.md": "# Testing"})
    dest = tmp_path / "standards" / "python"

    written = extract_pack_zip(zb, dest)

    assert sorted(p.name for p in written) == ["guide.md", "testing.md"]
    assert (dest / "guide.md").read_text() == "# Guide"
    assert (dest / "testing.md").read_text() == "# Testing"


def test_extract_pack_zip_flattens_directory_structure(tmp_path):
    """Even if an archive entry has a path (e.g. from a careless zip -r), only
    the basename is ever used as the destination filename -- this is also what
    makes path traversal via a crafted archive structurally impossible."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("subdir/guide.md", "# Guide")
        zf.writestr("../../etc/passwd", "malicious")

    dest = tmp_path / "standards" / "python"
    written = extract_pack_zip(buf.getvalue(), dest)

    names = sorted(p.name for p in written)
    assert names == ["guide.md", "passwd"]
    assert (dest / "guide.md").exists()
    assert (dest / "passwd").exists()
    assert all(dest in p.parents for p in written)


def test_extract_pack_zip_bad_zip_raises(tmp_path):
    with pytest.raises(RegistryFetchError, match="not a valid zip"):
        extract_pack_zip(b"not a zip file", tmp_path / "dest")


def test_extract_pack_zip_overwrites_existing_files(tmp_path):
    dest = tmp_path / "standards" / "python"
    dest.mkdir(parents=True)
    (dest / "guide.md").write_text("old content")

    zb = _zip_bytes({"guide.md": "new content"})
    extract_pack_zip(zb, dest)

    assert (dest / "guide.md").read_text() == "new content"


# ---------------------------------------------------------------------------
# extract_skills_zip (preserves <skill-name>/SKILL.md nesting)
# ---------------------------------------------------------------------------

def test_extract_skills_zip_preserves_skill_name_subdirectory(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("archaeology/SKILL.md", "# Archaeology skill")
        zf.writestr("recall/SKILL.md", "# Recall skill")

    skills_root = tmp_path / ".claude" / "skills"
    written = extract_skills_zip(buf.getvalue(), skills_root)

    assert sorted(str(p.relative_to(skills_root)) for p in written) == [
        "archaeology/SKILL.md", "recall/SKILL.md",
    ]
    assert (skills_root / "archaeology" / "SKILL.md").read_text() == "# Archaeology skill"
    assert (skills_root / "recall" / "SKILL.md").read_text() == "# Recall skill"


def test_extract_skills_zip_flat_entries_without_subdirectory_are_skipped(tmp_path):
    """An entry with no <skill-name>/ prefix doesn't match any valid skill
    layout -- skip it rather than guessing, since there's no skill name to
    create a directory for."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("loose-file.md", "orphan")
        zf.writestr("archaeology/SKILL.md", "# Archaeology skill")

    skills_root = tmp_path / ".claude" / "skills"
    written = extract_skills_zip(buf.getvalue(), skills_root)

    assert len(written) == 1
    assert (skills_root / "archaeology" / "SKILL.md").exists()
    assert not (skills_root / "loose-file.md").exists()


def test_extract_skills_zip_traversal_entry_cannot_escape_skills_root(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "malicious")
        zf.writestr("good-skill/SKILL.md", "# Good skill")

    skills_root = tmp_path / ".claude" / "skills"
    written = extract_skills_zip(buf.getvalue(), skills_root)

    # "../../etc/passwd" has parts ("..", "..", "etc", "passwd") -> last two
    # components are ("etc", "passwd"), so it lands at skills_root/etc/passwd,
    # never escaping skills_root.
    assert all(skills_root in p.parents for p in written)


def test_extract_skills_zip_bad_zip_raises(tmp_path):
    with pytest.raises(RegistryFetchError, match="not a valid zip"):
        extract_skills_zip(b"not a zip file", tmp_path / "dest")
