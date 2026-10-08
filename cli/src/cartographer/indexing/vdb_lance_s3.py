"""Central VDB driver: LanceDB on S3.

Implements the same logical interface as the pgvector driver it replaces
(vdb_pgvector.py), reusing the local LanceDB driver's (vdb.py) schema and
upsert semantics, but points lancedb.connect() at an s3:// URI instead of a
local path or a PostgreSQL connection.

Chosen because this project's central Postgres-compatible cluster is Aurora
DSQL, which rejects CREATE EXTENSION outright ("unsupported statement") --
pgvector is not an option there, confirmed live against the real cluster, not
just a config/permissions gap. See the ECS deployment plan's "Central VDB:
Lance-on-S3" step. Used only for the global scope (central topology); local
scope always uses the embedded LanceDB driver in vdb.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lancedb
import pyarrow as pa

from cartographer.indexing.vdb import (
    DEFAULT_EMBEDDING_DIM,
    ChunkRecord,
    _migrate_schema,
    _schema,
    _table_names,
)


def _table_name(project_id: str) -> str:
    safe = project_id.replace("-", "_")
    return f"carto_{safe}_global"


@dataclass
class LanceS3Driver:
    bucket: str
    prefix: str = "vdb"
    region: str = ""

    def _uri(self) -> str:
        prefix = self.prefix.strip("/")
        return f"s3://{self.bucket}/{prefix}" if prefix else f"s3://{self.bucket}"

    def _connect(self) -> lancedb.DBConnection:
        # No explicit aws_access_key_id/secret here on purpose: both developer
        # machines (via the VPN-reachable AWS CLI profile) and the ECS task
        # role rely on the default AWS credential chain. Region is passed
        # explicitly since it isn't always auto-discoverable from the URI alone.
        storage_options = {"aws_region": self.region} if self.region else None
        return lancedb.connect(self._uri(), storage_options=storage_options)

    def ensure_collection(self, project_id: str, embedding_dim: int = DEFAULT_EMBEDDING_DIM):
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name in _table_names(db):
            table = db.open_table(table_name)
            _migrate_schema(table, embedding_dim)
            return table
        return db.create_table(table_name, schema=_schema(embedding_dim))

    def upsert(self, project_id: str, chunks: list[ChunkRecord], embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> int:
        if not chunks:
            return 0
        table = self.ensure_collection(project_id, embedding_dim)
        data = pa.Table.from_pylist([c.model_dump() for c in chunks], schema=_schema(embedding_dim))
        table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        return len(chunks)

    def query(
        self,
        project_id: str,
        embedding: list[float],
        k: int = 8,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return []
        table = db.open_table(table_name)
        search = table.search(embedding).limit(k)
        if where:
            search = search.where(where)
        return search.to_list()

    def delete(self, project_id: str, ids: list[str]) -> None:
        if not ids:
            return
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return
        table = db.open_table(table_name)
        quoted = ", ".join(f"'{item}'" for item in ids)
        table.delete(f"id IN ({quoted})")

    def query_all_paths(self, project_id: str) -> list[str]:
        """Return all distinct paths currently in the global index for this project."""
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return []
        table = db.open_table(table_name)
        rows = table.search().select(["path"]).where("is_tombstone = false").to_list()
        return sorted({row["path"] for row in rows})

    def tombstone_path(self, project_id: str, path: str) -> None:
        """Mark all chunks for the given path as tombstoned in the global index."""
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return
        table = db.open_table(table_name)
        escaped = path.replace("'", "''")
        table.update(where=f"path = '{escaped}'", values={"is_tombstone": True})

    def query_by_path(self, project_id: str, path: str) -> dict[str, Any] | None:
        """Fetch the most recent non-tombstoned chunk for a specific path."""
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return None
        table = db.open_table(table_name)
        escaped = path.replace("'", "''")
        rows = table.search().where(f"path = '{escaped}' AND is_tombstone = false").to_list()
        if not rows:
            return None
        return max(rows, key=lambda row: row["updated_at"])

    def collection_stats(self, project_id: str) -> dict[str, int]:
        db = self._connect()
        table_name = _table_name(project_id)
        if table_name not in _table_names(db):
            return {}
        table = db.open_table(table_name)
        stats: dict[str, int] = {}
        for row in table.search().select(["artifact_type"]).to_list():
            stats[row["artifact_type"]] = stats.get(row["artifact_type"], 0) + 1
        return stats

    def is_reachable(self) -> bool:
        try:
            db = self._connect()
            _table_names(db)
            return True
        except Exception:
            return False
