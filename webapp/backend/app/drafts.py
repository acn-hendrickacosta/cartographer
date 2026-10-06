"""Draft/review state (SR.3), in the same Postgres database as SR.2's
registry tokens -- see app/db.py's docstring.

A draft edits one file within one pack's one content type, not a whole pack
archive -- see sr-3-webapp-authoring-and-publish.md's "Publish flow" section
for why. State machine: DRAFT -> IN_REVIEW -> APPROVED -> PUBLISHED, with
REJECTED -> DRAFT (revise and resubmit). One-approval model (OQ-09): any
Reviewer other than the draft's own author may approve/reject; enforced here
server-side (app/main.py's route handlers check this), not just hidden in
the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import get_connection

DRAFT_COLUMNS = "id, pack_name, content_type, file_name, target_version, author_email, content, state, created_at, updated_at"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "pack_name": row[1],
        "content_type": row[2],
        "file_name": row[3],
        "target_version": row[4],
        "author_email": row[5],
        "content": row[6],
        "state": row[7],
        "created_at": row[8].isoformat(),
        "updated_at": row[9].isoformat(),
    }


def create_draft(pack_name: str, content_type: str, file_name: str, target_version: str, author_email: str, content: str) -> dict:
    draft_id = str(uuid.uuid4())
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO drafts (id, pack_name, content_type, file_name, target_version, author_email, content)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {DRAFT_COLUMNS}""",
            (draft_id, pack_name, content_type, file_name, target_version, author_email, content),
        )
        row = cur.fetchone()
    return _row_to_dict(row)


def get_draft(draft_id: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {DRAFT_COLUMNS} FROM drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def update_draft(draft_id: str, content: str, target_version: str) -> dict | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE drafts SET content = %s, target_version = %s, updated_at = %s
                WHERE id = %s AND state = 'DRAFT'
                RETURNING {DRAFT_COLUMNS}""",
            (content, target_version, datetime.now(timezone.utc), draft_id),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def delete_draft(draft_id: str) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM drafts WHERE id = %s AND state = 'DRAFT'", (draft_id,))
        return cur.rowcount > 0


def transition(draft_id: str, from_states: tuple[str, ...], to_state: str) -> dict | None:
    """Generic state-machine move: only succeeds if the draft is currently in
    one of from_states, atomically (the WHERE clause is the guard -- no
    separate read-then-write race window)."""
    placeholders = ", ".join(["%s"] * len(from_states))
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE drafts SET state = %s, updated_at = %s
                WHERE id = %s AND state IN ({placeholders})
                RETURNING {DRAFT_COLUMNS}""",
            (to_state, datetime.now(timezone.utc), draft_id, *from_states),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_in_review() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {DRAFT_COLUMNS} FROM drafts WHERE state = 'IN_REVIEW' ORDER BY updated_at ASC")
        rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def add_comment(draft_id: str, author_email: str, body: str) -> dict:
    comment_id = str(uuid.uuid4())
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO draft_comments (id, draft_id, author_email, body)
               VALUES (%s, %s, %s, %s)
               RETURNING id, draft_id, author_email, body, created_at""",
            (comment_id, draft_id, author_email, body),
        )
        row = cur.fetchone()
    return {"id": row[0], "draft_id": row[1], "author_email": row[2], "body": row[3], "created_at": row[4].isoformat()}


def list_comments(draft_id: str) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, draft_id, author_email, body, created_at FROM draft_comments WHERE draft_id = %s ORDER BY created_at ASC",
            (draft_id,),
        )
        rows = cur.fetchall()
    return [{"id": r[0], "draft_id": r[1], "author_email": r[2], "body": r[3], "created_at": r[4].isoformat()} for r in rows]
