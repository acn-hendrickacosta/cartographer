"""Local VDB driver: an embedded LanceDB instance.

Schema per PROJECT_BRIEF.md Section 7.1. One logical collection per project; here
that maps to one LanceDB table per scope ("local" or "global") inside the project's
own on-disk database directory, so a single project never shares physical storage
with another.

Written as a small, reusable driver so the future MCP `vdb` server (Section 6.5) can
reuse this same on-disk database and upsert semantics instead of reimplementing them.
"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa
from pydantic import BaseModel

DEFAULT_EMBEDDING_DIM = 384  # matches fastembed's default local model output size


class ChunkRecord(BaseModel):
    id: str  # artifact identity + chunk ordinal, see artifact_id.chunk_id
    project_id: str
    scope: str  # "local" | "global"
    artifact_type: str  # code | doc | spec
    path: str
    symbol: str | None = None
    spec_id: str | None = None
    origin: str  # "local" | "global"
    text: str
    embedding: list[float]
    updated_at: str


def _schema(embedding_dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("project_id", pa.string()),
            pa.field("scope", pa.string()),
            pa.field("artifact_type", pa.string()),
            pa.field("path", pa.string()),
            pa.field("symbol", pa.string()),
            pa.field("spec_id", pa.string()),
            pa.field("origin", pa.string()),
            pa.field("text", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), embedding_dim)),
            pa.field("updated_at", pa.string()),
        ]
    )


def _connect(db_path: Path) -> lancedb.DBConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(db_path))


def _table_names(db: lancedb.DBConnection) -> list[str]:
    return db.list_tables().tables


def ensure_collection(db_path: Path, scope: str, embedding_dim: int = DEFAULT_EMBEDDING_DIM):
    """Create the per-scope table if absent. Idempotent."""
    db = _connect(db_path)
    if scope in _table_names(db):
        return db.open_table(scope)
    return db.create_table(scope, schema=_schema(embedding_dim))


def upsert(db_path: Path, scope: str, chunks: list[ChunkRecord], embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> int:
    """Idempotent upsert keyed by `id` (artifact identity + chunk ordinal)."""
    if not chunks:
        return 0
    table = ensure_collection(db_path, scope, embedding_dim)
    data = pa.Table.from_pylist([c.model_dump() for c in chunks], schema=_schema(embedding_dim))
    table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
    return len(chunks)


def query(
    db_path: Path,
    scope: str,
    embedding: list[float],
    k: int = 8,
    where: str | None = None,
) -> list[dict]:
    if scope not in _table_names(_connect(db_path)):
        return []
    table = ensure_collection(db_path, scope, len(embedding))
    search = table.search(embedding).limit(k)
    if where:
        search = search.where(where)
    return search.to_list()


def delete(db_path: Path, scope: str, ids: list[str]) -> None:
    if not ids:
        return
    db = _connect(db_path)
    if scope not in _table_names(db):
        return
    table = db.open_table(scope)
    quoted = ", ".join(f"'{item}'" for item in ids)
    table.delete(f"id IN ({quoted})")


def is_readable(db_path: Path) -> bool:
    """doctor helper: confirm the database directory opens without error."""
    try:
        _connect(db_path)
        return True
    except Exception:
        return False
