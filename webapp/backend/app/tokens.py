"""Registry token store: validates the per-project bearer tokens the CLI
sends to GET /api/packs/:name/content/:content_type, and (as of SR.4) issues,
lists, and revokes them.

Tokens are opaque; only their SHA-256 hash is ever stored or looked up,
matching the handling described in docs/components/standards-webapp.md Sec 9.
The raw token value is returned to the caller exactly once, at issuance
(`issue_token`'s return value) -- it is never persisted and never appears in
any subsequent read.

**Migrated 2026-10-05 from DynamoDB to Postgres** (`app/db.py`), reusing the
same instance the CLI's central VDB backend already runs -- see db.py's
docstring and settings.py's database_url comment. Schema (run once, by hand,
against the `cartographer_webapp` database):

    CREATE TABLE registry_tokens (
        token_hash TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at TIMESTAMPTZ,
        last_used_at TIMESTAMPTZ  -- added SR.4
    );
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from app.db import get_connection


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_token(token: str) -> str | None:
    """Return the project_id for a valid, non-revoked token, or None if the
    token is unknown or has been revoked. Never raises for a missing/invalid
    token -- that's an expected, common case for the caller (a 401), not an
    error condition.

    Bumps last_used_at on success -- a write on the read-heavy CLI-fetch path,
    but the admin screen showing "last used" (SR.4) needs it from somewhere,
    and a registry fetch is infrequent enough (once per `stack add`/`init`
    invocation) for this to be a non-issue."""
    if not token:
        return None
    token_hash = _hash_token(token)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT project_id, revoked_at FROM registry_tokens WHERE token_hash = %s",
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        project_id, revoked_at = row
        if revoked_at is not None:
            return None
        cur.execute(
            "UPDATE registry_tokens SET last_used_at = %s WHERE token_hash = %s",
            (datetime.now(timezone.utc), token_hash),
        )
    return project_id


def issue_token(project_id: str) -> str:
    """Generates a new opaque token, stores only its hash, and returns the
    raw value -- the only time it's ever available. Callers (the admin API
    route) must show it to the Admin immediately and never log or persist it
    themselves."""
    token = f"sr-{secrets.token_urlsafe(32)}"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO registry_tokens (token_hash, project_id) VALUES (%s, %s)",
            (_hash_token(token), project_id),
        )
    return token


def list_tokens() -> list[dict]:
    """Never returns the token value itself -- only the hash (safe to show;
    it's a one-way function, not a secret) plus metadata."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT token_hash, project_id, created_at, revoked_at, last_used_at FROM registry_tokens ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
    return [
        {
            "token_hash": r[0],
            "project_id": r[1],
            "created_at": r[2].isoformat(),
            "revoked_at": r[3].isoformat() if r[3] else None,
            "last_used_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def revoke_token(token_hash: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE registry_tokens SET revoked_at = %s WHERE token_hash = %s AND revoked_at IS NULL",
            (datetime.now(timezone.utc), token_hash),
        )
        return cur.rowcount > 0
