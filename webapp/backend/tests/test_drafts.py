"""Draft/review state (app/drafts.py), against a mocked Postgres connection."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app import drafts


def _fake_connection(fetchone_result=None, fetchall_result=None, rowcount=0):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_result
    mock_cursor.fetchall.return_value = fetchall_result or []
    mock_cursor.rowcount = rowcount
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    return fake_get_connection, mock_cursor


def _draft_row(state="DRAFT"):
    now = datetime.now(timezone.utc)
    return ("draft-1", "python", "standards", "testing.md", "2.0.0", "author@example.com", "new content", state, now, now)


def test_create_draft_returns_dict():
    fake_get_connection, mock_cursor = _fake_connection(fetchone_result=_draft_row())
    with patch.object(drafts, "get_connection", fake_get_connection):
        result = drafts.create_draft("python", "standards", "testing.md", "2.0.0", "author@example.com", "new content")
    assert result["pack_name"] == "python"
    assert result["state"] == "DRAFT"
    assert result["id"] == "draft-1"


def test_get_draft_not_found_returns_none():
    fake_get_connection, _ = _fake_connection(fetchone_result=None)
    with patch.object(drafts, "get_connection", fake_get_connection):
        assert drafts.get_draft("nope") is None


def test_update_draft_only_succeeds_in_draft_state():
    fake_get_connection, mock_cursor = _fake_connection(fetchone_result=None)
    with patch.object(drafts, "get_connection", fake_get_connection):
        result = drafts.update_draft("draft-1", "x", "2.0.0")
    assert result is None  # WHERE state = 'DRAFT' guard returned no row


def test_delete_draft_returns_false_when_no_rows_affected():
    fake_get_connection, mock_cursor = _fake_connection(rowcount=0)
    with patch.object(drafts, "get_connection", fake_get_connection):
        assert drafts.delete_draft("draft-1") is False


def test_delete_draft_returns_true_when_deleted():
    fake_get_connection, mock_cursor = _fake_connection(rowcount=1)
    with patch.object(drafts, "get_connection", fake_get_connection):
        assert drafts.delete_draft("draft-1") is True


def test_transition_atomic_guard_in_sql():
    fake_get_connection, mock_cursor = _fake_connection(fetchone_result=_draft_row(state="IN_REVIEW"))
    with patch.object(drafts, "get_connection", fake_get_connection):
        result = drafts.transition("draft-1", ("DRAFT",), "IN_REVIEW")
    assert result["state"] == "IN_REVIEW"
    sql = mock_cursor.execute.call_args[0][0]
    assert "WHERE id = %s AND state IN (%s)" in sql


def test_transition_fails_silently_when_state_does_not_match():
    fake_get_connection, _ = _fake_connection(fetchone_result=None)
    with patch.object(drafts, "get_connection", fake_get_connection):
        result = drafts.transition("draft-1", ("DRAFT",), "IN_REVIEW")
    assert result is None


def test_list_in_review():
    fake_get_connection, _ = _fake_connection(fetchall_result=[_draft_row(state="IN_REVIEW")])
    with patch.object(drafts, "get_connection", fake_get_connection):
        result = drafts.list_in_review()
    assert len(result) == 1
    assert result[0]["state"] == "IN_REVIEW"


def test_add_and_list_comments():
    now = datetime.now(timezone.utc)
    fake_get_connection, _ = _fake_connection(
        fetchone_result=("c1", "draft-1", "reviewer@example.com", "looks good", now)
    )
    with patch.object(drafts, "get_connection", fake_get_connection):
        comment = drafts.add_comment("draft-1", "reviewer@example.com", "looks good")
    assert comment["body"] == "looks good"

    fake_get_connection2, _ = _fake_connection(
        fetchall_result=[("c1", "draft-1", "reviewer@example.com", "looks good", now)]
    )
    with patch.object(drafts, "get_connection", fake_get_connection2):
        comments = drafts.list_comments("draft-1")
    assert len(comments) == 1
