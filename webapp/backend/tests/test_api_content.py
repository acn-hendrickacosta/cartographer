"""GET /api/packs/:name/content/:content_type -- the CLI's fetch endpoint.
Covers the auth and not-found paths with mocked tokens/S3; the happy path
plus every other screen is also proven against the real Cognito/S3/Postgres
resources (see docs/phases/sr-2-webapp-auth-and-read-views.md's status note)
-- these tests exist so the behavior is pinned in CI without needing live
AWS access.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import packs_admin, s3_registry, tokens
from app.main import app

client = TestClient(app)


def test_no_authorization_header_returns_401():
    resp = client.get("/api/packs/python/content/standards")
    assert resp.status_code == 401
    assert "Authorization" in resp.json()["detail"]


def test_malformed_authorization_header_returns_401():
    resp = client.get("/api/packs/python/content/standards", headers={"Authorization": "Basic abc123"})
    assert resp.status_code == 401


def test_invalid_content_type_returns_422():
    resp = client.get(
        "/api/packs/python/content/not-a-real-type", headers={"Authorization": "Bearer whatever"}
    )
    assert resp.status_code == 422


def test_invalid_token_returns_401():
    with patch.object(tokens, "validate_token", return_value=None):
        resp = client.get("/api/packs/python/content/standards", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
    assert "invalid or revoked" in resp.json()["detail"]


def test_valid_token_unpublished_pack_returns_404():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "get_latest", return_value=None):
        resp = client.get(
            "/api/packs/nonexistent/content/standards", headers={"Authorization": "Bearer good-token"}
        )
    assert resp.status_code == 404


def test_valid_token_missing_content_type_returns_404():
    """e.g. 'core' has no standards at all -- same 404 as an unpublished pack,
    not an error. See s3_registry.get_content_zip's docstring."""
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "get_latest", return_value={"pack": "core", "version": "1.0.0"}), \
         patch.object(s3_registry, "get_content_zip", return_value=None):
        resp = client.get("/api/packs/core/content/standards", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 404
    assert "no published standards" in resp.json()["detail"]


def _global_only(pack_name, project_id=None):
    """get_latest side_effect for a project with no fork: the project-scoped
    call (project_id="proj_x") returns None, only the global call (no
    project_id) returns the pack -- same shape api_pack_content actually
    calls it with (see SR.5's fork-first resolution)."""
    return None if project_id else {"pack": "python", "version": "1.2.3"}


def test_valid_token_success_returns_zip_with_version_header():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "get_latest", side_effect=_global_only), \
         patch.object(s3_registry, "get_content_zip", return_value=b"fake-zip-bytes") as mock_get_zip:
        resp = client.get("/api/packs/python/content/skills", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.headers["X-Pack-Version"] == "1.2.3"
    assert resp.content == b"fake-zip-bytes"
    assert resp.headers["content-type"] == "application/zip"
    mock_get_zip.assert_called_once_with("python", "1.2.3", "skills", project_id=None)


# ---------------------------------------------------------------------------
# SR.5: per-project forks
# ---------------------------------------------------------------------------

def test_fork_scoped_project_gets_served_its_own_fork_not_baseline():
    def latest_side_effect(pack_name, project_id=None):
        if project_id == "proj_x":
            return {"pack": "python", "version": s3_registry.FORK_VERSION}
        return {"pack": "python", "version": "1.2.3"}  # global baseline -- must not be used

    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "get_latest", side_effect=latest_side_effect), \
         patch.object(s3_registry, "get_content_zip", return_value=b"forked-zip-bytes") as mock_get_zip:
        resp = client.get("/api/packs/python/content/standards", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.headers["X-Pack-Version"] == s3_registry.FORK_VERSION
    assert resp.content == b"forked-zip-bytes"
    mock_get_zip.assert_called_once_with("python", s3_registry.FORK_VERSION, "standards", project_id="proj_x")


def test_fork_pack_already_forked_returns_409():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=True):
        resp = client.post("/api/packs/python/fork", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 409


def test_fork_pack_no_baseline_and_not_registered_returns_404():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=False), \
         patch.object(s3_registry, "get_latest", return_value=None), \
         patch.object(packs_admin, "pack_exists", return_value=False):
        resp = client.post("/api/packs/nope/fork", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 404
    assert "not registered" in resp.json()["detail"]


def test_fork_pack_no_baseline_but_registered_creates_empty_fork():
    """An enterprise-exclusive pack that was never published globally -- only
    registered via /api/admin/packs -- can still be forked; the result has
    forked_from: None rather than a real baseline version."""
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=False), \
         patch.object(s3_registry, "get_latest", return_value=None), \
         patch.object(packs_admin, "pack_exists", return_value=True), \
         patch.object(s3_registry, "fork_pack_for_project", return_value={"pack": "acme-harness", "version": "fork", "forked_from": None}):
        resp = client.post("/api/packs/acme-harness/fork", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json() == {"pack": "acme-harness", "version": "fork", "forked_from": None}


def test_fork_pack_success_returns_fork_result():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=False), \
         patch.object(s3_registry, "get_latest", return_value={"pack": "python", "version": "1.2.3"}), \
         patch.object(s3_registry, "fork_pack_for_project", return_value={"pack": "python", "version": "fork", "forked_from": "1.2.3"}):
        resp = client.post("/api/packs/python/fork", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json() == {"pack": "python", "version": "fork", "forked_from": "1.2.3"}


def test_push_fork_content_no_fork_yet_returns_404():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=False):
        resp = client.put(
            "/api/packs/python/fork/standards", headers={"Authorization": "Bearer good-token"}, content=b"zip-bytes"
        )
    assert resp.status_code == 404
    assert "stack fork" in resp.json()["detail"]


def test_push_fork_content_success_writes_raw_body_to_fork_version():
    with patch.object(tokens, "validate_token", return_value="proj_x"), \
         patch.object(s3_registry, "project_has_fork", return_value=True), \
         patch.object(s3_registry, "put_content_zip") as mock_put:
        resp = client.put(
            "/api/packs/python/fork/standards", headers={"Authorization": "Bearer good-token"}, content=b"zip-bytes"
        )
    assert resp.status_code == 200
    mock_put.assert_called_once_with("python", s3_registry.FORK_VERSION, "standards", b"zip-bytes", project_id="proj_x")
