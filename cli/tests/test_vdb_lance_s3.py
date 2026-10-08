"""LanceS3Driver: central VDB on S3, used instead of pgvector when the central
Postgres-compatible cluster doesn't support extensions (e.g. Aurora DSQL).

These tests exercise the real LanceDB query/upsert/tombstone logic end to end
by pointing the driver at a local directory instead of a real s3:// URI --
the only S3-specific code is `_uri()`/`_connect()`'s storage_options, which a
local directory doesn't exercise, so that part is covered separately by
`test_uri_and_connect_args` below via a patched `lancedb.connect`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import lancedb

from cartographer.indexing.vdb import ChunkRecord
from cartographer.indexing.vdb_lance_s3 import LanceS3Driver, _table_name


def _local_driver(tmp_path: Path) -> LanceS3Driver:
    """A LanceS3Driver whose _connect() opens a local directory instead of S3."""
    driver = LanceS3Driver(bucket="unused", prefix="unused", region="")
    driver._connect = lambda: lancedb.connect(str(tmp_path / "lance_db"))  # type: ignore[method-assign]
    return driver


def _chunk(chunk_id: str, path: str, text: str = "hello", is_tombstone: bool = False, updated_at: str = "2026-01-01T00:00:00Z") -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        project_id="proj_1",
        scope="global",
        artifact_type="code",
        path=path,
        origin="global",
        text=text,
        embedding=[0.1] * 384,
        updated_at=updated_at,
        is_tombstone=is_tombstone,
    )


def test_table_name_sanitizes_project_id():
    assert _table_name("proj-abc-123") == "carto_proj_abc_123_global"


def test_upsert_and_query_roundtrip(tmp_path):
    driver = _local_driver(tmp_path)
    count = driver.upsert("proj_1", [_chunk("c1", "src/a.py"), _chunk("c2", "src/b.py")])
    assert count == 2

    hits = driver.query("proj_1", embedding=[0.1] * 384, k=5)
    assert {h["id"] for h in hits} == {"c1", "c2"}


def test_upsert_is_idempotent_on_id(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert("proj_1", [_chunk("c1", "src/a.py", text="v1")])
    driver.upsert("proj_1", [_chunk("c1", "src/a.py", text="v2")])

    rows = driver.query_by_path("proj_1", "src/a.py")
    assert rows is not None
    assert rows["text"] == "v2"


def test_query_empty_when_table_absent(tmp_path):
    driver = _local_driver(tmp_path)
    assert driver.query("proj_never_seeded", embedding=[0.1] * 384) == []
    assert driver.query_all_paths("proj_never_seeded") == []
    assert driver.query_by_path("proj_never_seeded", "x") is None
    assert driver.collection_stats("proj_never_seeded") == {}


def test_delete_removes_rows(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert("proj_1", [_chunk("c1", "src/a.py"), _chunk("c2", "src/b.py")])
    driver.delete("proj_1", ["c1"])

    hits = driver.query("proj_1", embedding=[0.1] * 384, k=5)
    assert {h["id"] for h in hits} == {"c2"}


def test_tombstone_path_marks_rows_and_excludes_from_paths(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert("proj_1", [_chunk("c1", "src/a.py"), _chunk("c2", "src/b.py")])

    driver.tombstone_path("proj_1", "src/a.py")

    assert driver.query_all_paths("proj_1") == ["src/b.py"]
    assert driver.query_by_path("proj_1", "src/a.py") is None


def test_query_by_path_returns_most_recent(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert(
        "proj_1",
        [
            _chunk("c1", "src/a.py", text="old", updated_at="2026-01-01T00:00:00Z"),
            _chunk("c2", "src/a.py", text="new", updated_at="2026-02-01T00:00:00Z"),
        ],
    )

    row = driver.query_by_path("proj_1", "src/a.py")
    assert row is not None
    assert row["text"] == "new"


def test_collection_stats_counts_by_artifact_type(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert(
        "proj_1",
        [
            _chunk("c1", "src/a.py"),
            _chunk("c2", "src/b.py"),
            ChunkRecord(
                id="c3", project_id="proj_1", scope="global", artifact_type="doc",
                path="docs/x.md", origin="global", text="t", embedding=[0.1] * 384,
                updated_at="2026-01-01T00:00:00Z",
            ),
        ],
    )

    assert driver.collection_stats("proj_1") == {"code": 2, "doc": 1}


def test_is_reachable_true_on_success(tmp_path):
    driver = _local_driver(tmp_path)
    assert driver.is_reachable() is True


def test_is_reachable_false_on_connect_error(tmp_path):
    driver = LanceS3Driver(bucket="unused")
    driver._connect = lambda: (_ for _ in ()).throw(RuntimeError("no network"))  # type: ignore[method-assign]
    assert driver.is_reachable() is False


def test_upsert_noop_on_empty_chunks(tmp_path):
    driver = _local_driver(tmp_path)
    assert driver.upsert("proj_1", []) == 0


def test_delete_noop_on_empty_ids(tmp_path):
    driver = _local_driver(tmp_path)
    driver.upsert("proj_1", [_chunk("c1", "src/a.py")])
    driver.delete("proj_1", [])
    assert driver.query("proj_1", embedding=[0.1] * 384) != []


# ---------------------------------------------------------------------------
# S3-specific wiring: URI construction and storage_options passed to connect()
# ---------------------------------------------------------------------------

def test_uri_joins_bucket_and_prefix():
    driver = LanceS3Driver(bucket="my-bucket", prefix="vdb")
    assert driver._uri() == "s3://my-bucket/vdb"


def test_uri_strips_leading_and_trailing_slashes_in_prefix():
    driver = LanceS3Driver(bucket="my-bucket", prefix="/vdb/")
    assert driver._uri() == "s3://my-bucket/vdb"


def test_uri_with_empty_prefix_is_bucket_root():
    driver = LanceS3Driver(bucket="my-bucket", prefix="")
    assert driver._uri() == "s3://my-bucket"


def test_connect_passes_region_as_storage_option():
    driver = LanceS3Driver(bucket="my-bucket", prefix="vdb", region="us-east-1")
    with patch("cartographer.indexing.vdb_lance_s3.lancedb.connect") as mock_connect:
        driver._connect()
        mock_connect.assert_called_once_with("s3://my-bucket/vdb", storage_options={"aws_region": "us-east-1"})


def test_connect_passes_no_storage_options_when_region_unset():
    driver = LanceS3Driver(bucket="my-bucket", prefix="vdb", region="")
    with patch("cartographer.indexing.vdb_lance_s3.lancedb.connect") as mock_connect:
        driver._connect()
        mock_connect.assert_called_once_with("s3://my-bucket/vdb", storage_options=None)
