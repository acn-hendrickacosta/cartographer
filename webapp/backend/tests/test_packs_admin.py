"""Pack name registry (app/packs_admin.py), against a mocked Postgres connection."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app import packs_admin


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


def test_list_packs_returns_dicts():
    now = datetime.now(timezone.utc)
    rows = [("core", None, now), ("python", now, now)]
    fake_get_connection, _ = _fake_connection(fetchall_result=rows)
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        result = packs_admin.list_packs()
    assert result == [
        {"name": "core", "deprecated_at": None, "created_at": now.isoformat()},
        {"name": "python", "deprecated_at": now.isoformat(), "created_at": now.isoformat()},
    ]


def test_create_pack_returns_none_when_name_exists():
    fake_get_connection, _ = _fake_connection(fetchone_result=(1,))
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.create_pack("python") is None


def test_create_pack_returns_dict_for_new_name():
    now = datetime.now(timezone.utc)
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [None, ("new-pack", None, now)]
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    with patch.object(packs_admin, "get_connection", fake_get_connection):
        result = packs_admin.create_pack("new-pack")
    assert result == {"name": "new-pack", "deprecated_at": None, "created_at": now.isoformat()}


def test_pack_exists_true_for_registered_pack():
    fake_get_connection, _ = _fake_connection(fetchone_result=(1,))
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.pack_exists("python") is True


def test_pack_exists_false_for_unregistered_pack():
    fake_get_connection, _ = _fake_connection(fetchone_result=None)
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.pack_exists("nope") is False


def test_is_deprecated_false_for_active_pack():
    fake_get_connection, _ = _fake_connection(fetchone_result=(None,))
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.is_deprecated("python") is False


def test_is_deprecated_true_for_deprecated_pack():
    now = datetime.now(timezone.utc)
    fake_get_connection, _ = _fake_connection(fetchone_result=(now,))
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.is_deprecated("python") is True


def test_is_deprecated_false_for_unknown_pack():
    fake_get_connection, _ = _fake_connection(fetchone_result=None)
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.is_deprecated("nope") is False


def test_deprecate_pack_returns_none_when_already_deprecated_or_unknown():
    fake_get_connection, _ = _fake_connection(fetchone_result=None)
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        assert packs_admin.deprecate_pack("python") is None


def test_deprecate_pack_returns_dict_on_success():
    now = datetime.now(timezone.utc)
    fake_get_connection, _ = _fake_connection(fetchone_result=("python", now, now))
    with patch.object(packs_admin, "get_connection", fake_get_connection):
        result = packs_admin.deprecate_pack("python")
    assert result == {"name": "python", "deprecated_at": now.isoformat(), "created_at": now.isoformat()}
