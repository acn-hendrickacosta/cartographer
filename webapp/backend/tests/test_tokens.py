"""Registry token validation (app/tokens.py), against a mocked Postgres
connection (app/db.get_connection). See test_db.py-equivalent coverage note:
there's no separate integration test hitting the real container here -- that
was done manually during the DynamoDB->Postgres migration (see
docs/phases/sr-2-webapp-auth-and-read-views.md's status note) via `docker exec
... psql` and a live server request.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app import tokens


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fake_connection(fetchone_result):
    """Builds a fake get_connection() context manager yielding a connection
    whose cursor's fetchone() returns the given row (or None)."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_result
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    return fake_get_connection, mock_cursor


def test_validate_token_empty_string_returns_none_without_db_call():
    fake_get_connection, mock_cursor = _fake_connection(None)
    with patch.object(tokens, "get_connection", fake_get_connection):
        result = tokens.validate_token("")
    assert result is None
    mock_cursor.execute.assert_not_called()


def test_validate_token_unknown_token_returns_none():
    fake_get_connection, _ = _fake_connection(None)
    with patch.object(tokens, "get_connection", fake_get_connection):
        result = tokens.validate_token("unknown-token")
    assert result is None


def test_validate_token_valid_token_returns_project_id():
    token = "sk-valid-token"
    fake_get_connection, mock_cursor = _fake_connection(("proj_x", None))
    with patch.object(tokens, "get_connection", fake_get_connection):
        result = tokens.validate_token(token)
    assert result == "proj_x"
    # First call reads the row; second bumps last_used_at -- both against the
    # same hash, so this also covers the SR.4 "last used" tracking addition.
    assert mock_cursor.execute.call_count == 2
    select_call, update_call = mock_cursor.execute.call_args_list
    assert select_call.args == (
        "SELECT project_id, revoked_at FROM registry_tokens WHERE token_hash = %s",
        (_hash(token),),
    )
    assert update_call.args[0] == "UPDATE registry_tokens SET last_used_at = %s WHERE token_hash = %s"
    assert update_call.args[1][1] == _hash(token)


def test_validate_token_revoked_token_returns_none():
    import datetime
    fake_get_connection, mock_cursor = _fake_connection(("proj_x", datetime.datetime.now(datetime.timezone.utc)))
    with patch.object(tokens, "get_connection", fake_get_connection):
        result = tokens.validate_token("sk-revoked-token")
    assert result is None
    # A revoked token must not have its last_used_at bumped.
    mock_cursor.execute.assert_called_once()


def test_issue_token_returns_raw_value_and_stores_only_its_hash():
    fake_get_connection, mock_cursor = _fake_connection(None)
    with patch.object(tokens, "get_connection", fake_get_connection):
        token = tokens.issue_token("proj_x")
    assert token.startswith("sr-")
    insert_sql, params = mock_cursor.execute.call_args.args
    assert "INSERT INTO registry_tokens" in insert_sql
    assert params == (_hash(token), "proj_x")


def test_list_tokens_never_includes_raw_token_value():
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    row = (_hash("sr-abc"), "proj_x", now, None, None)
    fake_get_connection, mock_cursor = _fake_connection(None)
    mock_cursor.fetchall.return_value = [row]
    with patch.object(tokens, "get_connection", fake_get_connection):
        result = tokens.list_tokens()
    assert result == [
        {
            "token_hash": _hash("sr-abc"),
            "project_id": "proj_x",
            "created_at": now.isoformat(),
            "revoked_at": None,
            "last_used_at": None,
        }
    ]
    assert "sr-abc" not in str(result)


def test_revoke_token_returns_true_when_a_row_was_updated():
    fake_get_connection, mock_cursor = _fake_connection(None)
    mock_cursor.rowcount = 1
    with patch.object(tokens, "get_connection", fake_get_connection):
        assert tokens.revoke_token(_hash("sr-abc")) is True


def test_revoke_token_returns_false_when_already_revoked_or_unknown():
    fake_get_connection, mock_cursor = _fake_connection(None)
    mock_cursor.rowcount = 0
    with patch.object(tokens, "get_connection", fake_get_connection):
        assert tokens.revoke_token(_hash("sr-abc")) is False
