"""SR.3 draft/review/publish API routes. Role and ownership checks are the
important thing to pin here -- the one-approval model (OQ-09) and
author-only-edits are enforced server-side in app/main.py, not just hidden
in the UI, so these tests exercise the HTTP layer directly rather than
re-testing app/drafts.py's SQL (see test_drafts.py for that)."""

from __future__ import annotations

import json
from base64 import b64encode
from unittest.mock import patch

import itsdangerous
from fastapi.testclient import TestClient

from app import drafts, publish, s3_registry
from app.main import app
from app.settings import settings

client = TestClient(app)


def _session_cookie(email, groups):
    signer = itsdangerous.TimestampSigner(settings.session_secret)
    session = {"user": {"email": email, "groups": groups}}
    data = b64encode(json.dumps(session).encode("utf-8"))
    return signer.sign(data).decode("utf-8")


def _as(email, groups):
    client.cookies.set("session", _session_cookie(email, groups))
    return client


def _draft(**overrides):
    base = {
        "id": "draft-1", "pack_name": "python", "content_type": "standards", "file_name": "testing.md",
        "target_version": "2.0.0", "author_email": "author@example.com", "content": "x",
        "state": "DRAFT", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def teardown_function(_):
    client.cookies.clear()


# ---------------------------------------------------------------------------
# Create / update / discard -- author-only
# ---------------------------------------------------------------------------

def test_create_draft_requires_author_role():
    _as("someone@example.com", ["Reviewer"])
    resp = client.post("/api/drafts", json={
        "pack_name": "python", "content_type": "standards", "file_name": "x.md",
        "target_version": "2.0.0", "content": "hi",
    })
    assert resp.status_code == 403


def test_create_draft_succeeds_for_author():
    with patch.object(drafts, "create_draft", return_value=_draft()):
        _as("author@example.com", ["Author"])
        resp = client.post("/api/drafts", json={
            "pack_name": "python", "content_type": "standards", "file_name": "testing.md",
            "target_version": "2.0.0", "content": "x",
        })
    assert resp.status_code == 200
    assert resp.json()["pack_name"] == "python"


def test_update_draft_rejects_non_author():
    with patch.object(drafts, "get_draft", return_value=_draft(author_email="author@example.com")):
        _as("someone-else@example.com", ["Author"])
        resp = client.patch("/api/drafts/draft-1", json={"content": "y", "target_version": "2.0.0"})
    assert resp.status_code == 403


def test_update_draft_rejects_non_draft_state():
    with patch.object(drafts, "get_draft", return_value=_draft(author_email="author@example.com")), \
         patch.object(drafts, "update_draft", return_value=None):
        _as("author@example.com", ["Author"])
        resp = client.patch("/api/drafts/draft-1", json={"content": "y", "target_version": "2.0.0"})
    assert resp.status_code == 409


def test_discard_draft_requires_ownership():
    with patch.object(drafts, "get_draft", return_value=_draft(author_email="author@example.com")):
        _as("someone-else@example.com", ["Author"])
        resp = client.delete("/api/drafts/draft-1")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Submit -- version-ordering check
# ---------------------------------------------------------------------------

def test_submit_rejects_version_not_higher_than_published():
    draft = _draft(author_email="author@example.com", target_version="1.0.0")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}):
        _as("author@example.com", ["Author"])
        resp = client.post("/api/drafts/draft-1/submit")
    assert resp.status_code == 400
    assert "must be higher" in resp.json()["detail"]


def test_submit_succeeds_when_version_is_higher():
    draft = _draft(author_email="author@example.com", target_version="2.0.0")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(s3_registry, "get_latest", return_value={"version": "1.0.0"}), \
         patch.object(drafts, "transition", return_value=draft | {"state": "IN_REVIEW"}):
        _as("author@example.com", ["Author"])
        resp = client.post("/api/drafts/draft-1/submit")
    assert resp.status_code == 200
    assert resp.json()["state"] == "IN_REVIEW"


def test_submit_succeeds_with_no_prior_published_version():
    draft = _draft(author_email="author@example.com", pack_name="core")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(s3_registry, "get_latest", return_value=None), \
         patch.object(drafts, "transition", return_value=draft | {"state": "IN_REVIEW"}):
        _as("author@example.com", ["Author"])
        resp = client.post("/api/drafts/draft-1/submit")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Review queue -- Reviewer-only
# ---------------------------------------------------------------------------

def test_review_queue_requires_reviewer_role():
    _as("author@example.com", ["Author"])
    resp = client.get("/api/review-queue")
    assert resp.status_code == 403


def test_review_queue_lists_in_review_drafts():
    with patch.object(drafts, "list_in_review", return_value=[_draft(state="IN_REVIEW")]):
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.get("/api/review-queue")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Approve/reject -- one-approval model (OQ-09): not your own draft
# ---------------------------------------------------------------------------

def test_approve_rejects_own_draft():
    draft = _draft(author_email="reviewer@example.com", state="IN_REVIEW")
    with patch.object(drafts, "get_draft", return_value=draft):
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/approve")
    assert resp.status_code == 403
    assert "own author" in resp.json()["detail"]


def test_approve_succeeds_for_different_reviewer():
    draft = _draft(author_email="author@example.com", state="IN_REVIEW")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(drafts, "transition", return_value=draft | {"state": "APPROVED"}):
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/approve")
    assert resp.status_code == 200
    assert resp.json()["state"] == "APPROVED"


def test_reject_requires_non_empty_comment():
    draft = _draft(author_email="author@example.com", state="IN_REVIEW")
    with patch.object(drafts, "get_draft", return_value=draft):
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/reject", json={"comment": "   "})
    assert resp.status_code == 400


def test_reject_succeeds_and_adds_comment():
    draft = _draft(author_email="author@example.com", state="IN_REVIEW")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(drafts, "transition", return_value=draft | {"state": "REJECTED"}), \
         patch.object(drafts, "add_comment") as mock_add_comment:
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/reject", json={"comment": "needs work"})
    assert resp.status_code == 200
    mock_add_comment.assert_called_once_with("draft-1", "reviewer@example.com", "needs work")


def test_revise_requires_ownership():
    draft = _draft(author_email="author@example.com", state="REJECTED")
    with patch.object(drafts, "get_draft", return_value=draft):
        _as("someone-else@example.com", ["Author"])
        resp = client.post("/api/drafts/draft-1/revise")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Publish -- only from APPROVED, writes to S3 before flipping state
# ---------------------------------------------------------------------------

def test_publish_requires_approved_state():
    draft = _draft(state="IN_REVIEW")
    with patch.object(drafts, "get_draft", return_value=draft):
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/publish")
    assert resp.status_code == 409


def test_publish_calls_s3_then_transitions_state():
    draft = _draft(state="APPROVED")
    with patch.object(drafts, "get_draft", return_value=draft), \
         patch.object(publish, "publish_draft") as mock_publish, \
         patch.object(drafts, "transition", return_value=draft | {"state": "PUBLISHED"}) as mock_transition:
        _as("reviewer@example.com", ["Reviewer"])
        resp = client.post("/api/drafts/draft-1/publish")
    assert resp.status_code == 200
    assert resp.json()["state"] == "PUBLISHED"
    mock_publish.assert_called_once_with(draft)
    mock_transition.assert_called_once_with("draft-1", ("APPROVED",), "PUBLISHED")


def test_publish_requires_reviewer_role():
    _as("author@example.com", ["Author"])
    resp = client.post("/api/drafts/draft-1/publish")
    assert resp.status_code == 403
