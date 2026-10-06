"""Shared Postgres connection pool. One pool for the whole app -- tokens.py
uses it today; SR.3's draft/review tables will reuse it too, same instance,
same pattern, rather than each module opening its own connections.
"""

from __future__ import annotations

from contextlib import contextmanager

from psycopg2.pool import SimpleConnectionPool

from app.settings import settings

_pool: SimpleConnectionPool | None = None


def _get_pool() -> SimpleConnectionPool:
    # Lazy: SimpleConnectionPool opens `minconn` real connections at
    # construction time. Creating it at import time would mean any test or
    # process that imports app.tokens (and transitively this module) fails
    # immediately if Postgres isn't reachable yet, even for tests that never
    # touch the DB (they mock get_connection itself, but can't stop the
    # import-time side effect). Deferred to first actual use instead.
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=settings.database_url)
    return _pool


@contextmanager
def get_connection():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
