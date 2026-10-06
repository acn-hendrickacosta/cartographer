"""JSON API endpoints consumed by the React SPA: /api/me, /api/packs,
/api/packs/:name/:type, /api/packs/:name/:type/versions. All session-cookie
authenticated (Cognito), distinct from the CLI's bearer-token content endpoint
covered in test_api_content.py.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import s3_registry
from app.main import app

client = TestClient(app)


def _session_cookie(email="test-author@example.com", groups=None):
    import itsdangerous
    import json
    from base64 import b64encode

    from app.settings import settings

    signer = itsdangerous.TimestampSigner(settings.session_secret)
    session = {"user": {"email": email, "groups": groups or ["Author"]}}
    data = b64encode(json.dumps(session).encode("utf-8"))
    return signer.sign(data).decode("utf-8")


def test_api_me_without_session_returns_401():
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_api_me_with_session_returns_user():
    client.cookies.set("session", _session_cookie())
    resp = client.get("/api/me")
    client.cookies.clear()
    assert resp.status_code == 200
    assert resp.json() == {"email": "test-author@example.com", "groups": ["Author"]}


def test_api_packs_filters_by_content_type():
    client.cookies.set("session", _session_cookie())
    fake_index = {
        "core": {"1.0.0": {"skills", "agents"}},
        "python": {"1.0.0": {"standards", "skills", "agents"}},
        "angular": {"1.0.0": {"standards", "skills"}},
    }
    with patch.object(s3_registry, "list_registry_index", return_value=fake_index), \
         patch.object(s3_registry, "get_latest_many", return_value={
             "core": {"version": "1.0.0"},
             "python": {"version": "1.0.0"},
             "angular": {"version": "1.0.0"},
         }):
        resp = client.get("/api/packs?type=agents")
    client.cookies.clear()
    assert resp.status_code == 200
    assert {p["name"] for p in resp.json()} == {"core", "python"}


def test_api_packs_sorted_by_name():
    client.cookies.set("session", _session_cookie())
    fake_index = {"vue": {"1.0.0": {"standards"}}, "angular": {"1.0.0": {"standards"}}}
    with patch.object(s3_registry, "list_registry_index", return_value=fake_index), \
         patch.object(s3_registry, "get_latest_many", return_value={
             "vue": {"version": "1.0.0"}, "angular": {"version": "1.0.0"},
         }):
        resp = client.get("/api/packs?type=standards")
    client.cookies.clear()
    assert [p["name"] for p in resp.json()] == ["angular", "vue"]


def test_api_packs_requires_session():
    resp = client.get("/api/packs?type=standards")
    assert resp.status_code == 401


def test_api_pack_detail_flattens_skills_to_path_keys():
    client.cookies.set("session", _session_cookie())
    with patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=b"fake-zip"), \
         patch.object(s3_registry, "list_skills_in_zip", return_value={"archaeology": {"SKILL.md": "# Archaeology"}}), \
         patch.object(s3_registry, "get_version_metadata", return_value={"changelog": "x"}):
        resp = client.get("/api/packs/core/skills")
    client.cookies.clear()
    assert resp.status_code == 200
    assert resp.json()["files"] == {"archaeology/SKILL.md": "# Archaeology"}


def test_api_pack_detail_standards_returns_flat_files():
    client.cookies.set("session", _session_cookie())
    with patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=b"fake-zip"), \
         patch.object(s3_registry, "list_files_in_zip", return_value={"guide.md": "# Guide"}), \
         patch.object(s3_registry, "get_version_metadata", return_value=None):
        resp = client.get("/api/packs/python/standards")
    client.cookies.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "python"
    assert body["version"] == "1.0.0"
    assert body["files"] == {"guide.md": "# Guide"}


def test_api_pack_detail_missing_content_type_returns_404():
    client.cookies.set("session", _session_cookie())
    with patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=None):
        resp = client.get("/api/packs/core/standards")
    client.cookies.clear()
    assert resp.status_code == 404


def test_api_pack_versions_filters_by_content_type_and_sorts_descending():
    client.cookies.set("session", _session_cookie())
    with patch.object(s3_registry, "list_versions", return_value=["1.0.0", "2.0.0"]), \
         patch.object(s3_registry, "available_content_types", return_value=["standards"]), \
         patch.object(s3_registry, "get_version_metadata", side_effect=lambda name, v: {"changelog": v}):
        resp = client.get("/api/packs/python/standards/versions")
    client.cookies.clear()
    assert resp.status_code == 200
    versions = resp.json()
    assert [v["version"] for v in versions] == ["2.0.0", "1.0.0"]
