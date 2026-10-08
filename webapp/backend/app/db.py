"""Shared Postgres connection pool. One pool for the whole app -- tokens.py
uses it today; SR.3's draft/review tables will reuse it too, same instance,
same pattern, rather than each module opening its own connections.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import psycopg2
from psycopg2.pool import AbstractConnectionPool, SimpleConnectionPool

from app.settings import settings

_pool: AbstractConnectionPool | None = None


def _get_pool() -> AbstractConnectionPool:
    # Lazy: opening the pool does real connection I/O at construction time.
    # Creating it at import time would mean any test or process that imports
    # app.tokens (and transitively this module) fails immediately if the
    # database isn't reachable yet, even for tests that never touch the DB
    # (they mock get_connection itself, but can't stop the import-time side
    # effect). Deferred to first actual use instead.
    global _pool
    if _pool is None:
        if settings.db_driver == "dsql":
            # Aurora DSQL has no passwords -- a plain psycopg2 pool with a
            # fixed DSN would bake in one IAM token at pool-creation time and
            # start failing on any new connection opened after that token
            # expires (default 15 min). This connector's pool overrides just
            # _connect() to generate a fresh token per physical connection;
            # everything else is unchanged psycopg2.pool.ThreadedConnectionPool.
            import aurora_dsql_psycopg2 as dsql

            _pool = dsql.AuroraDSQLThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                dbname=settings.db_name,
                region=settings.aws_region,
                sslmode="require",
            )
        else:
            _pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=settings.database_url)
    return _pool


def _is_live(conn: Any) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg2.OperationalError:
        return False


@contextmanager
def get_connection():
    pool = _get_pool()
    conn = pool.getconn()
    if settings.db_driver == "dsql" and not _is_live(conn):
        # DSQL force-closes connections server-side after ~1 hour regardless
        # of the pool's own bookkeeping (psycopg2.pool has no built-in
        # recycling, unlike the newer psycopg3 pool AWS's docs recommend
        # max_lifetime for). Discard the stale connection and get a fresh one
        # -- _connect() generates a new token for it -- rather than fail the
        # request outright.
        pool.putconn(conn, close=True)
        conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
