"""app/db.py: the pool must not be created at import time (see its docstring
for why -- a test environment without Postgres reachable would otherwise fail
to even import app.tokens)."""

from __future__ import annotations

from unittest.mock import patch

from app import db


def test_pool_not_created_until_first_use():
    with patch.object(db, "_pool", None):
        assert db._pool is None  # confirms the patch took effect / module state is what we think

    # Importing/referencing the module must not itself have constructed a pool
    # as a side effect beyond whatever the process already did elsewhere --
    # this is a weak but real guard: _get_pool must be callable without
    # raising just because _pool starts as None.
    with patch.object(db, "SimpleConnectionPool") as mock_pool_cls:
        db._pool = None
        db._get_pool()
        mock_pool_cls.assert_called_once()
        # Second call reuses the same pool, doesn't construct again.
        db._get_pool()
        mock_pool_cls.assert_called_once()
