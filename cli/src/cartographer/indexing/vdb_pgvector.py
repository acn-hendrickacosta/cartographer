"""Central VDB driver: PostgreSQL + pgvector.

Implements the same logical interface as the local LanceDB driver (vdb.py) but
writes to a PostgreSQL instance with the pgvector extension. Used only for the
global scope (central topology). Local scope always uses LanceDB.

Requires: psycopg2-binary (install with: pip install "cartographer[central]")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cartographer.indexing.vdb import ChunkRecord


def _table_name(project_id: str) -> str:
    safe = project_id.replace("-", "_")
    return f"carto_{safe}_global"


@dataclass
class PgvectorDriver:
    host: str
    port: int
    user: str
    password: str
    database: str

    def _connect(self):
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError(
                "psycopg2 is required for pgvector support. "
                "Install with: pip install \"cartographer[central]\""
            ) from exc
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.database,
        )

    def ensure_collection(self, project_id: str, embedding_dim: int = 384) -> None:
        table = _table_name(project_id)
        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {table} (
                            id TEXT PRIMARY KEY,
                            project_id TEXT NOT NULL,
                            scope TEXT NOT NULL,
                            artifact_type TEXT NOT NULL,
                            path TEXT NOT NULL,
                            symbol TEXT,
                            spec_id TEXT,
                            origin TEXT NOT NULL,
                            text TEXT NOT NULL,
                            embedding vector({embedding_dim}),
                            updated_at TEXT NOT NULL
                        )
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS {table}_embedding_idx
                        ON {table} USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 100)
                    """)
        finally:
            conn.close()

    def upsert(self, project_id: str, chunks: list[ChunkRecord], embedding_dim: int = 384) -> int:
        if not chunks:
            return 0
        self.ensure_collection(project_id, embedding_dim)
        table = _table_name(project_id)
        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    for chunk in chunks:
                        cur.execute(f"""
                            INSERT INTO {table}
                                (id, project_id, scope, artifact_type, path, symbol,
                                 spec_id, origin, text, embedding, updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET
                                project_id   = EXCLUDED.project_id,
                                scope        = EXCLUDED.scope,
                                artifact_type = EXCLUDED.artifact_type,
                                path         = EXCLUDED.path,
                                symbol       = EXCLUDED.symbol,
                                spec_id      = EXCLUDED.spec_id,
                                origin       = EXCLUDED.origin,
                                text         = EXCLUDED.text,
                                embedding    = EXCLUDED.embedding,
                                updated_at   = EXCLUDED.updated_at
                        """, (
                            chunk.id, chunk.project_id, chunk.scope,
                            chunk.artifact_type, chunk.path, chunk.symbol,
                            chunk.spec_id, chunk.origin, chunk.text,
                            chunk.embedding, chunk.updated_at,
                        ))
        finally:
            conn.close()
        return len(chunks)

    def query(
        self,
        project_id: str,
        embedding: list[float],
        k: int = 8,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        table = _table_name(project_id)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                where_clause = f"AND ({where})" if where else ""
                cur.execute(f"""
                    SELECT id, project_id, scope, artifact_type, path,
                           symbol, spec_id, origin, text, updated_at,
                           1 - (embedding <=> %s::vector) AS score
                    FROM {table}
                    WHERE true {where_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (embedding, embedding, k))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def delete(self, project_id: str, ids: list[str]) -> None:
        if not ids:
            return
        table = _table_name(project_id)
        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", (ids,))
        finally:
            conn.close()

    def collection_stats(self, project_id: str) -> dict[str, int]:
        table = _table_name(project_id)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT artifact_type, COUNT(*) as cnt
                    FROM {table} GROUP BY artifact_type
                """)
                return {row[0]: row[1] for row in cur.fetchall()}
        except Exception:
            return {}
        finally:
            conn.close()

    def is_reachable(self) -> bool:
        try:
            conn = self._connect()
            conn.close()
            return True
        except ImportError:
            raise  # let caller surface the missing-package message
        except Exception:
            return False
