"""Pack name registry (SR.4), in the same Postgres database as SR.2/SR.3's
other state.

This exists because S3 alone can't represent "a pack name exists but has no
content yet" -- `s3_registry.list_packs()` derives names purely from S3
prefixes, so a brand-new pack with zero published content wouldn't show up
anywhere. The `packs` table is the authoritative list of pack names (seeded
once with the 13 that already existed before this phase); S3 content
existence is a separate, independent question answered by s3_registry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db import get_connection


def list_packs() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name, deprecated_at, created_at FROM packs ORDER BY name ASC")
        rows = cur.fetchall()
    return [{"name": r[0], "deprecated_at": r[1].isoformat() if r[1] else None, "created_at": r[2].isoformat()} for r in rows]


def create_pack(name: str) -> dict | None:
    """Returns None if the name already exists -- the route handler turns
    that into a 409, not a 500."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM packs WHERE name = %s", (name,))
        if cur.fetchone():
            return None
        cur.execute(
            "INSERT INTO packs (name) VALUES (%s) RETURNING name, deprecated_at, created_at",
            (name,),
        )
        row = cur.fetchone()
    return {"name": row[0], "deprecated_at": None, "created_at": row[2].isoformat()}


def is_deprecated(name: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT deprecated_at FROM packs WHERE name = %s", (name,))
        row = cur.fetchone()
    return bool(row and row[0])


def deprecate_pack(name: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE packs SET deprecated_at = %s WHERE name = %s AND deprecated_at IS NULL
               RETURNING name, deprecated_at, created_at""",
            (datetime.now(timezone.utc), name),
        )
        row = cur.fetchone()
    return {"name": row[0], "deprecated_at": row[1].isoformat(), "created_at": row[2].isoformat()} if row else None
