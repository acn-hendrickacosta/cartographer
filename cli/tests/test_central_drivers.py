"""Integration tests for the central backend drivers: PgvectorDriver and Neo4jDriver.

These tests require running backend instances. They are skipped automatically when
the backends are not reachable. To run them locally with Docker Compose:

    docker compose -f tests/docker-compose.yml up -d
    pytest tests/test_central_drivers.py -m integration

Environment variables (or defaults used in docker-compose.yml):
    CARTO_TEST_PG_HOST      (default: localhost)
    CARTO_TEST_PG_PORT      (default: 5432)
    CARTO_TEST_PG_USER      (default: cartographer)
    CARTO_TEST_PG_PASSWORD  (default: cartographer)
    CARTO_TEST_PG_DB        (default: cartographer_test)
    CARTO_TEST_NEO4J_URI    (default: bolt://localhost:7687)
    CARTO_TEST_NEO4J_USER   (default: neo4j)
    CARTO_TEST_NEO4J_PASS   (default: cartographer)
"""

from __future__ import annotations

import os
import uuid

import pytest

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

PG_HOST     = os.environ.get("CARTO_TEST_PG_HOST", "localhost")
PG_PORT     = int(os.environ.get("CARTO_TEST_PG_PORT", "5432"))
PG_USER     = os.environ.get("CARTO_TEST_PG_USER", "cartographer")
PG_PASSWORD = os.environ.get("CARTO_TEST_PG_PASSWORD", "cartographer")
PG_DB       = os.environ.get("CARTO_TEST_PG_DB", "cartographer_test")

NEO4J_URI   = os.environ.get("CARTO_TEST_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER  = os.environ.get("CARTO_TEST_NEO4J_USER", "neo4j")
NEO4J_PASS  = os.environ.get("CARTO_TEST_NEO4J_PASS", "cartographer")


def _make_pgvector_driver():
    from cartographer.indexing.vdb_pgvector import PgvectorDriver
    return PgvectorDriver(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASSWORD, database=PG_DB,
    )


def _make_neo4j_driver():
    from cartographer.indexing.kg_neo4j import Neo4jDriver
    return Neo4jDriver(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)


def _pgvector_available() -> bool:
    try:
        drv = _make_pgvector_driver()
        return drv.is_reachable()
    except Exception:
        return False


def _neo4j_available() -> bool:
    try:
        drv = _make_neo4j_driver()
        return drv.is_reachable()
    except Exception:
        return False


pgvector_only = pytest.mark.skipif(
    not _pgvector_available(),
    reason="pgvector backend not reachable (set CARTO_TEST_PG_* env vars or run docker compose)",
)
neo4j_only = pytest.mark.skipif(
    not _neo4j_available(),
    reason="Neo4j backend not reachable (set CARTO_TEST_NEO4J_* env vars or run docker compose)",
)
integration = pytest.mark.integration


def _chunk(project_id: str, suffix: str = "", path: str = "src/auth.py") -> "ChunkRecord":
    from cartographer.indexing.vdb import ChunkRecord
    return ChunkRecord(
        id=f"{project_id}/{path}:0{suffix}",
        project_id=project_id,
        scope="global",
        artifact_type="code",
        path=path,
        symbol=None,
        spec_id=None,
        origin="local",
        text=f"def login(): pass{suffix}",
        embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _node(project_id: str, node_id: str | None = None, path: str = "src/auth.py"):
    from cartographer.indexing.kg import Node
    nid = node_id or f"{project_id}/{path}"
    return Node(id=nid, project_id=project_id, scope="global",
                type="module", path=path, attrs="{}")


def _edge(src: str, dst: str, edge_type: str = "imports"):
    from cartographer.indexing.kg import Edge
    return Edge(src=src, dst=dst, type=edge_type, scope="global", attrs="{}")


# ---------------------------------------------------------------------------
# PgvectorDriver tests
# ---------------------------------------------------------------------------

class TestPgvectorDriver:

    @integration
    @pgvector_only
    def test_is_reachable(self):
        assert _make_pgvector_driver().is_reachable()

    @integration
    @pgvector_only
    def test_ensure_collection_idempotent(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        drv.ensure_collection(pid, embedding_dim=384)  # second call must not raise

    @integration
    @pgvector_only
    def test_upsert_and_query(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        c = _chunk(pid)
        drv.upsert(pid, [c], embedding_dim=384)
        results = drv.query(pid, embedding=[0.1] * 384, k=1)
        assert len(results) == 1
        assert results[0]["id"] == c.id

    @integration
    @pgvector_only
    def test_upsert_is_idempotent(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        c = _chunk(pid)
        drv.upsert(pid, [c], embedding_dim=384)
        drv.upsert(pid, [c], embedding_dim=384)  # same id, must not duplicate
        stats = drv.collection_stats(pid)
        assert stats.get("code", 0) == 1

    @integration
    @pgvector_only
    def test_upsert_updates_existing(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        from cartographer.indexing.vdb import ChunkRecord
        c1 = _chunk(pid)
        drv.upsert(pid, [c1], embedding_dim=384)
        c2 = ChunkRecord(**{**c1.__dict__, "text": "def login(): return True"})
        drv.upsert(pid, [c2], embedding_dim=384)
        results = drv.query(pid, embedding=[0.1] * 384, k=1)
        assert results[0]["text"] == "def login(): return True"

    @integration
    @pgvector_only
    def test_delete(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        c = _chunk(pid)
        drv.upsert(pid, [c], embedding_dim=384)
        drv.delete(pid, [c.id])
        stats = drv.collection_stats(pid)
        assert stats.get("code", 0) == 0

    @integration
    @pgvector_only
    def test_delete_nonexistent_is_noop(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        drv.delete(pid, ["does_not_exist"])  # must not raise

    @integration
    @pgvector_only
    def test_collection_stats(self):
        drv = _make_pgvector_driver()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        drv.ensure_collection(pid, embedding_dim=384)
        drv.upsert(pid, [_chunk(pid, path="src/auth.py"), _chunk(pid, suffix="b", path="src/config.py")], embedding_dim=384)
        stats = drv.collection_stats(pid)
        assert stats.get("code", 0) == 2


# ---------------------------------------------------------------------------
# Neo4jDriver tests
# ---------------------------------------------------------------------------

class TestNeo4jDriver:

    @integration
    @neo4j_only
    def test_is_reachable(self):
        assert _make_neo4j_driver().is_reachable()

    @integration
    @neo4j_only
    def test_ensure_namespace_idempotent(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        drv.ensure_namespace()  # second call must not raise

    @integration
    @neo4j_only
    def test_upsert_nodes(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        node = _node(pid)
        drv.upsert_nodes([node])
        result = drv.query("MATCH (a:Artifact {id: $id}) RETURN a.id AS id", {"id": node.id})
        assert len(result) == 1
        assert result[0]["id"] == node.id

    @integration
    @neo4j_only
    def test_upsert_nodes_idempotent(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        node = _node(pid)
        drv.upsert_nodes([node])
        drv.upsert_nodes([node])
        result = drv.query("MATCH (a:Artifact {id: $id}) RETURN count(*) AS cnt", {"id": node.id})
        assert result[0]["cnt"] == 1

    @integration
    @neo4j_only
    def test_upsert_edges(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        src_node = _node(pid, path="src/auth.py")
        dst_node = _node(pid, path="src/config.py")
        drv.upsert_nodes([src_node, dst_node])
        edge = _edge(src_node.id, dst_node.id)
        drv.upsert_edges([edge])
        result = drv.query(
            "MATCH (s:Artifact {id: $src})-[r:RELATES_TO]->(d:Artifact {id: $dst}) RETURN r.type AS type",
            {"src": src_node.id, "dst": dst_node.id},
        )
        assert len(result) == 1
        assert result[0]["type"] == "imports"

    @integration
    @neo4j_only
    def test_upsert_edges_idempotent(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        src = _node(pid, path="src/a.py")
        dst = _node(pid, path="src/b.py")
        drv.upsert_nodes([src, dst])
        e = _edge(src.id, dst.id)
        drv.upsert_edges([e])
        drv.upsert_edges([e])
        result = drv.query(
            "MATCH (s:Artifact {id: $src})-[r:RELATES_TO]->(d:Artifact {id: $dst}) RETURN count(*) AS cnt",
            {"src": src.id, "dst": dst.id},
        )
        assert result[0]["cnt"] == 1

    @integration
    @neo4j_only
    def test_neighbors_depth_1(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        n1 = _node(pid, path="src/a.py")
        n2 = _node(pid, path="src/b.py")
        drv.upsert_nodes([n1, n2])
        drv.upsert_edges([_edge(n1.id, n2.id)])
        neighbors = drv.neighbors(n1.id, depth=1)
        neighbor_ids = [n["id"] for n in neighbors]
        assert n2.id in neighbor_ids

    @integration
    @neo4j_only
    def test_neighbors_depth_2(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        n1 = _node(pid, path="src/a.py")
        n2 = _node(pid, path="src/b.py")
        n3 = _node(pid, path="src/c.py")
        drv.upsert_nodes([n1, n2, n3])
        drv.upsert_edges([_edge(n1.id, n2.id), _edge(n2.id, n3.id)])
        neighbors = drv.neighbors(n1.id, depth=2)
        neighbor_ids = [n["id"] for n in neighbors]
        assert n3.id in neighbor_ids

    @integration
    @neo4j_only
    def test_delete_nodes_cascade_deletes_edges(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        src = _node(pid, path="src/a.py")
        dst = _node(pid, path="src/b.py")
        drv.upsert_nodes([src, dst])
        drv.upsert_edges([_edge(src.id, dst.id)])
        drv.delete_nodes([src.id])
        result = drv.query(
            "MATCH ()-[r:RELATES_TO]->(d:Artifact {id: $id}) RETURN count(*) AS cnt",
            {"id": dst.id},
        )
        assert result[0]["cnt"] == 0

    @integration
    @neo4j_only
    def test_namespace_stats(self):
        drv = _make_neo4j_driver()
        drv.ensure_namespace()
        pid = f"test_{uuid.uuid4().hex[:8]}"
        n1 = _node(pid, path="src/a.py")
        n2 = _node(pid, path="src/b.py")
        drv.upsert_nodes([n1, n2])
        drv.upsert_edges([_edge(n1.id, n2.id)])
        stats = drv.namespace_stats()
        assert stats["nodes"] >= 2
        assert stats["edges"] >= 1


# ---------------------------------------------------------------------------
# Promote integration test (requires both backends)
# ---------------------------------------------------------------------------

both_backends = pytest.mark.skipif(
    not (_pgvector_available() and _neo4j_available()),
    reason="both pgvector and Neo4j must be reachable for the promote integration test",
)


@integration
@both_backends
def test_promote_idempotent(tmp_path):
    """Promote artifacts to global scope twice; counts must be identical."""
    from cartographer.indexing.vdb_pgvector import PgvectorDriver
    from cartographer.indexing.kg_neo4j import Neo4jDriver
    from cartographer.indexing.vdb import ChunkRecord
    from cartographer.indexing.kg import Node, Edge

    pid = f"test_{uuid.uuid4().hex[:8]}"
    vdb = _make_pgvector_driver()
    kg = _make_neo4j_driver()
    vdb.ensure_collection(pid, embedding_dim=384)
    kg.ensure_namespace()

    chunks = [_chunk(pid)]
    nodes = [_node(pid)]
    edges: list[Edge] = []

    def do_promote():
        vdb.upsert(pid, chunks, embedding_dim=384)
        kg.upsert_nodes(nodes)
        if edges:
            kg.upsert_edges(edges)

    do_promote()
    stats_after_first = vdb.collection_stats(pid)
    do_promote()
    stats_after_second = vdb.collection_stats(pid)
    assert stats_after_first == stats_after_second


# ---------------------------------------------------------------------------
# Phase 3.2: Tombstone integration tests (exit criteria 1–6)
# ---------------------------------------------------------------------------

@integration
@pgvector_only
def test_tombstone_path_sets_flag_in_pgvector(tmp_path):
    """Exit criterion 1: tombstone_path marks is_tombstone=True for all chunks at path."""
    drv = _make_pgvector_driver()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    drv.ensure_collection(pid, embedding_dim=384)
    c = _chunk(pid, path="src/deleted.py")
    drv.upsert(pid, [c], embedding_dim=384)

    # Confirm chunk is visible before tombstone
    results_before = drv.query(pid, embedding=[0.1] * 384, k=5)
    assert any(r["path"] == "src/deleted.py" for r in results_before)

    drv.tombstone_path(pid, "src/deleted.py")

    # Confirm chunk is excluded from query after tombstone (driver hard-filters is_tombstone=FALSE)
    results_after = drv.query(pid, embedding=[0.1] * 384, k=5)
    assert not any(r["path"] == "src/deleted.py" for r in results_after), (
        "tombstoned artifact must not appear in VDB query results"
    )

    # Confirm is_tombstone=TRUE in the raw table
    from cartographer.indexing.vdb_pgvector import _table_name
    table = _table_name(pid)
    conn = drv._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT is_tombstone FROM {table} WHERE path = %s", ("src/deleted.py",))
            rows = cur.fetchall()
        assert rows, "chunk not found in table"
        assert all(row[0] is True for row in rows), "is_tombstone must be TRUE after tombstone_path"
    finally:
        conn.close()


@integration
@neo4j_only
def test_set_tombstoned_marks_kg_node(tmp_path):
    """Exit criterion 2: set_tombstoned sets tombstoned_at on the KG node."""
    import datetime
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    node = _node(pid, path="src/deleted.py")
    drv.upsert_nodes([node])

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    drv.set_tombstoned("src/deleted.py", now)

    result = drv.query(
        "MATCH (a:Artifact {id: $id}) RETURN a.tombstoned_at AS ts",
        {"id": node.id},
    )
    assert result, "node not found after set_tombstoned"
    assert result[0]["ts"] == now, (
        f"tombstoned_at must equal the timestamp passed; got {result[0]['ts']!r}"
    )


@integration
@pgvector_only
def test_tombstoned_artifacts_excluded_from_recall(tmp_path):
    """Exit criterion 3: tombstoned artifacts do not appear in global VDB recall results."""
    drv = _make_pgvector_driver()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    drv.ensure_collection(pid, embedding_dim=384)
    live = _chunk(pid, path="src/live.py")
    dead = _chunk(pid, suffix="_dead", path="src/deleted.py")
    drv.upsert(pid, [live, dead], embedding_dim=384)

    drv.tombstone_path(pid, "src/deleted.py")

    results = drv.query(pid, embedding=[0.1] * 384, k=10)
    paths = [r["path"] for r in results]
    assert "src/live.py" in paths, "live artifact must appear in recall"
    assert "src/deleted.py" not in paths, "tombstoned artifact must be excluded from recall"


@integration
@neo4j_only
def test_tombstoned_kg_nodes_excluded_from_neighbors(tmp_path):
    """Exit criterion 4: tombstoned KG nodes do not appear in neighbor traversal."""
    import datetime
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    n_live = _node(pid, path="src/live.py")
    n_dead = _node(pid, path="src/deleted.py")
    n_root = _node(pid, path="src/root.py")
    drv.upsert_nodes([n_root, n_live, n_dead])
    drv.upsert_edges([_edge(n_root.id, n_live.id), _edge(n_root.id, n_dead.id)])

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    drv.set_tombstoned("src/deleted.py", now)

    neighbors = drv.neighbors(n_root.id, depth=1)
    neighbor_ids = [n["id"] for n in neighbors]
    assert n_live.id in neighbor_ids, "live neighbor must appear"
    assert n_dead.id not in neighbor_ids, "tombstoned neighbor must be excluded"


@integration
@pgvector_only
def test_query_all_paths_excludes_tombstoned(tmp_path):
    """query_all_paths returns only non-tombstoned paths — used by promote for deletion detection."""
    drv = _make_pgvector_driver()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    drv.ensure_collection(pid, embedding_dim=384)
    live = _chunk(pid, path="src/live.py")
    dead = _chunk(pid, suffix="_dead", path="src/deleted.py")
    drv.upsert(pid, [live, dead], embedding_dim=384)
    drv.tombstone_path(pid, "src/deleted.py")

    paths = drv.query_all_paths(pid)
    assert "src/live.py" in paths
    assert "src/deleted.py" not in paths


@integration
@both_backends
def test_gc_removes_tombstones_immediately(tmp_path, monkeypatch):
    """Exit criteria 5 & 6: gc --older-than 0 removes tombstoned artifacts; --dry-run does not."""
    import datetime
    from typer.testing import CliRunner
    from cartographer import config as config_mod, registry
    from cartographer.cli import app

    # Set up a minimal workspace pointing at the test Docker backends
    workspace = tmp_path / "proj"
    workspace.mkdir()
    (workspace / ".cartographer" / "local").mkdir(parents=True)

    pid = f"test_{uuid.uuid4().hex[:8]}"
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=pid, name="gc-test"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)

    override_path = workspace / "cartographer.local.toml"
    override_path.write_text(
        "[central_vdb]\n"
        f"host = \"{PG_HOST}\"\n"
        f"port = {PG_PORT}\n"
        f"user = \"{PG_USER}\"\n"
        f"password = \"{PG_PASSWORD}\"\n"
        f"database = \"{PG_DB}\"\n"
        "[central_kg]\n"
        f"uri = \"{NEO4J_URI}\"\n"
        f"user = \"{NEO4J_USER}\"\n"
        f"password = \"{NEO4J_PASS}\"\n"
    )

    # Seed a chunk and tombstone it
    vdb_drv = _make_pgvector_driver()
    vdb_drv.ensure_collection(pid, embedding_dim=384)
    c = _chunk(pid, path="src/to_delete.py")
    # Back-date updated_at so gc --older-than 0 picks it up immediately
    from cartographer.indexing.vdb import ChunkRecord
    c_old = ChunkRecord(**{**c.model_dump(), "updated_at": "2020-01-01T00:00:00+00:00"})
    vdb_drv.upsert(pid, [c_old], embedding_dim=384)
    vdb_drv.tombstone_path(pid, "src/to_delete.py")

    kg_drv = _make_neo4j_driver()
    kg_drv.ensure_namespace()
    node = _node(pid, path="src/to_delete.py")
    kg_drv.upsert_nodes([node])
    kg_drv.set_tombstoned("src/to_delete.py", "2020-01-01T00:00:00+00:00")

    # dry-run: nothing deleted
    result = CliRunner().invoke(app, ["gc", "--path", str(workspace), "--dry-run", "--older-than", "0"])
    assert result.exit_code == 0, f"gc --dry-run failed:\n{result.output}"
    assert "to_delete.py" in result.output

    # Confirm chunk still in table after dry-run
    from cartographer.indexing.vdb_pgvector import _table_name
    table = _table_name(pid)
    conn = vdb_drv._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE path = %s AND is_tombstone = TRUE", ("src/to_delete.py",))
            assert cur.fetchone()[0] == 1, "chunk must still exist after dry-run"
    finally:
        conn.close()

    # Real gc: chunk and node deleted
    result = CliRunner().invoke(app, ["gc", "--path", str(workspace), "--older-than", "0"])
    assert result.exit_code == 0, f"gc failed:\n{result.output}"
    assert "gc complete" in result.output

    conn = vdb_drv._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE path = %s", ("src/to_delete.py",))
            assert cur.fetchone()[0] == 0, "tombstoned chunk must be deleted after gc"
    finally:
        conn.close()

    kg_result = kg_drv.query(
        "MATCH (a:Artifact {id: $id}) RETURN count(*) AS cnt",
        {"id": node.id},
    )
    assert kg_result[0]["cnt"] == 0, "tombstoned KG node must be deleted after gc"


# ---------------------------------------------------------------------------
# Phase 3.3: Rename tracking integration tests
# ---------------------------------------------------------------------------

@integration
@neo4j_only
def test_find_supersedes_source_returns_new_path(tmp_path):
    """Exit criterion 2: a supersedes edge is written and queryable both ways."""
    import datetime
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    old_node = _node(pid, path="src/old_name.py")
    new_node = _node(pid, path="src/new_name.py")
    drv.upsert_nodes([old_node, new_node])

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    drv.upsert_edges([_edge(new_node.id, old_node.id, edge_type="supersedes")])
    drv.set_tombstoned("src/old_name.py", now)

    redirect = drv.find_supersedes_source("src/old_name.py")
    assert redirect is not None
    assert redirect["new_path"] == "src/new_name.py"


@integration
@neo4j_only
def test_find_supersedes_source_returns_none_when_absent(tmp_path):
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    node = _node(pid, path="src/deleted.py")
    drv.upsert_nodes([node])
    assert drv.find_supersedes_source("src/deleted.py") is None


@integration
@pgvector_only
def test_query_by_path_returns_latest_non_tombstoned(tmp_path):
    drv = _make_pgvector_driver()
    pid = f"test_{uuid.uuid4().hex[:8]}"
    drv.ensure_collection(pid, embedding_dim=384)
    c = _chunk(pid, path="src/new_name.py")
    drv.upsert(pid, [c], embedding_dim=384)

    result = drv.query_by_path(pid, "src/new_name.py")
    assert result is not None
    assert result["path"] == "src/new_name.py"

    drv.tombstone_path(pid, "src/new_name.py")
    assert drv.query_by_path(pid, "src/new_name.py") is None


@integration
@both_backends
def test_promote_rename_end_to_end(tmp_path):
    """Exit criteria 1-4, 7: full rename flow against real backends — supersedes
    edge written, old path tombstoned in both stores, new path content present,
    last_promoted_sha advances, and a second promote is idempotent (no duplicate
    supersedes edge, stable counts)."""
    import subprocess
    from unittest.mock import patch
    from typer.testing import CliRunner
    from cartographer import config as config_mod, registry
    from cartographer.cli import app

    pid = f"test_{uuid.uuid4().hex[:8]}"

    workspace = tmp_path / "proj"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=workspace, check=True, capture_output=True)

    (workspace / "src").mkdir()
    (workspace / "src" / "old_name.py").write_text("def hello(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/old_name.py"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add"], cwd=workspace, check=True, capture_output=True)
    pre_rename_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()

    subprocess.run(["git", "mv", "src/old_name.py", "src/new_name.py"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "rename"], cwd=workspace, check=True, capture_output=True)

    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=pid, name="rename-e2e"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)
    override_path = workspace / "cartographer.local.toml"
    override_path.write_text(
        "promotion_token = \"test-token\"\n"
        "[central_vdb]\n"
        f"host = \"{PG_HOST}\"\n"
        f"port = {PG_PORT}\n"
        f"user = \"{PG_USER}\"\n"
        f"password = \"{PG_PASSWORD}\"\n"
        f"database = \"{PG_DB}\"\n"
        "[central_kg]\n"
        f"uri = \"{NEO4J_URI}\"\n"
        f"user = \"{NEO4J_USER}\"\n"
        f"password = \"{NEO4J_PASS}\"\n"
    )

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    from cartographer.indexing import vdb as vdb_driver, kg as kg_driver
    from cartographer.indexing.vdb import ChunkRecord
    from cartographer.indexing.kg import Node

    chunk = ChunkRecord(
        id=f"{pid}/src/new_name.py:0", project_id=pid, scope="local",
        artifact_type="code", path="src/new_name.py", origin="local",
        text="def hello(): pass", embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    vdb_driver.upsert(local_dir / "vdb.lance", "local", [chunk])
    kg_driver.ensure_namespace(local_dir / "kg.kuzu")
    kg_driver.upsert_nodes(local_dir / "kg.kuzu", [Node(
        id="path:src/new_name.py", project_id=pid, scope="local",
        type="module", path="src/new_name.py", attrs="{}",
    )])

    reg_path = tmp_path / "registry.json"
    with patch.object(registry, "registry_path", lambda: reg_path):
        record = registry.register_project(pid, "rename-e2e", "central", "default", workspace)
        record.last_promoted_sha = pre_rename_sha
        registry.upsert_project(record)

        # Seed the global index with the old path, simulating a prior promote
        vdb_drv = _make_pgvector_driver()
        vdb_drv.ensure_collection(pid, embedding_dim=384)
        old_chunk = _chunk(pid, path="src/old_name.py")
        vdb_drv.upsert(pid, [old_chunk], embedding_dim=384)

        kg_drv = _make_neo4j_driver()
        kg_drv.ensure_namespace()
        old_node = _node(pid, path="src/old_name.py")
        kg_drv.upsert_nodes([old_node])

        result = CliRunner().invoke(app, ["promote", "--path", str(workspace), "--full"])
        assert result.exit_code == 0, result.output

        # old path tombstoned in both stores
        results = vdb_drv.query(pid, embedding=[0.1] * 384, k=10)
        assert not any(r["path"] == "src/old_name.py" for r in results)

        # supersedes edge present, pointing old -> new
        redirect = kg_drv.find_supersedes_source("src/old_name.py")
        assert redirect is not None
        assert redirect["new_path"] == "src/new_name.py"

        # new path content present via query_by_path
        new_content = vdb_drv.query_by_path(pid, "src/new_name.py")
        assert new_content is not None

        # last_promoted_sha advanced
        updated = registry.get_project(pid)
        new_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
        assert updated.last_promoted_sha == new_head

        # idempotent: promote again, counts/edges must not duplicate
        result2 = CliRunner().invoke(app, ["promote", "--path", str(workspace), "--full"])
        assert result2.exit_code == 0, result2.output
        redirect2 = kg_drv.find_supersedes_source("src/old_name.py")
        assert redirect2 == redirect


# ---------------------------------------------------------------------------
# Phase 3.4: Conflict detection integration test
# ---------------------------------------------------------------------------

@integration
@pgvector_only
def test_conflict_detected_end_to_end_via_recall(tmp_path, monkeypatch):
    """Developer A promotes a file; Developer B edits it locally without
    promoting; Developer B's recall must show a CONFLICT notice. After
    Developer B also promotes (timestamps now match), the notice disappears."""
    from typer.testing import CliRunner
    from unittest.mock import patch
    from cartographer import config as config_mod, registry
    from cartographer.cli import app
    from cartographer.indexing import vdb as vdb_driver
    from cartographer.indexing.vdb import ChunkRecord

    pid = f"test_{uuid.uuid4().hex[:8]}"
    vdb_drv = _make_pgvector_driver()
    vdb_drv.ensure_collection(pid, embedding_dim=384)

    # Developer A's promoted (global) version
    global_chunk = _chunk(pid, path="src/shared.py")
    vdb_drv.upsert(pid, [global_chunk], embedding_dim=384)

    # Developer B's local workspace, with a locally-edited (newer) version
    workspace = tmp_path / "proj"
    workspace.mkdir()
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id=pid, name="conflict-e2e"),
        topology=config_mod.TopologySection(mode="central"),
        isolation=config_mod.IsolationSection(tenant="default"),
    )
    config_mod.save_config(workspace, cfg)

    local_dir = workspace / ".cartographer" / "local"
    local_dir.mkdir(parents=True)
    local_chunk = ChunkRecord(
        id=f"{pid}/src/shared.py:0", project_id=pid, scope="local",
        artifact_type="code", path="src/shared.py", origin="local",
        text="def login(): return True  # locally edited", embedding=[0.1] * 384,
        updated_at="2026-06-01T00:00:00+00:00",
    )
    vdb_driver.upsert(local_dir / "vdb.lance", "local", [local_chunk])
    from cartographer.indexing import kg as kg_driver
    kg_driver.ensure_namespace(local_dir / "kg.kuzu")

    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "registry_path", lambda: reg_path)
    registry.register_project(pid, "conflict-e2e", "central", "default", workspace)

    with patch("cartographer.indexing.central.get_central_vdb", return_value=vdb_drv), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result = CliRunner().invoke(app, ["recall", "login", "--path", str(workspace)])

    assert result.exit_code == 0, result.output
    assert "CONFLICT" in result.output
    assert "src/shared.py" in result.output

    # Developer B promotes — global now matches local exactly (same updated_at)
    vdb_drv.upsert(pid, [ChunkRecord(**{**local_chunk.model_dump()})], embedding_dim=384)

    with patch("cartographer.indexing.central.get_central_vdb", return_value=vdb_drv), \
         patch("fastembed.TextEmbedding") as mock_embed:
        mock_embed.return_value.embed.return_value = iter([[0.1] * 384])
        result2 = CliRunner().invoke(app, ["recall", "login", "--path", str(workspace)])

    assert result2.exit_code == 0, result2.output
    assert "CONFLICT" not in result2.output


# ---------------------------------------------------------------------------
# Phase 4: kg_impact integration test (global scope, Neo4j)
# ---------------------------------------------------------------------------

@integration
@neo4j_only
def test_find_impact_excludes_tombstoned_dependents(tmp_path):
    """Exit criterion 4 (adapted): cross-project reverse traversal finds
    transitive dependents and excludes tombstoned ones."""
    import datetime
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"

    a = _node(pid, path="a.py")
    b = _node(pid, path="b.py")
    c = _node(pid, path="c.py")
    drv.upsert_nodes([a, b, c])
    drv.upsert_edges([
        _edge(b.id, a.id, edge_type="imports"),
        _edge(c.id, b.id, edge_type="imports"),
    ])

    rows = drv.find_impact(a.id, depth=4, edge_types=["imports"])
    assert {r["path"] for r in rows} == {"b.py", "c.py"}

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    drv.set_tombstoned("b.py", now)

    rows_after = drv.find_impact(a.id, depth=4, edge_types=["imports"])
    paths_after = {r["path"] for r in rows_after}
    assert "b.py" not in paths_after
    assert "c.py" in paths_after


@integration
@neo4j_only
def test_find_impact_respects_edge_type_filter(tmp_path):
    drv = _make_neo4j_driver()
    drv.ensure_namespace()
    pid = f"test_{uuid.uuid4().hex[:8]}"

    a = _node(pid, path="a.py")
    b = _node(pid, path="b.py")
    drv.upsert_nodes([a, b])
    drv.upsert_edges([_edge(b.id, a.id, edge_type="calls")])

    rows = drv.find_impact(a.id, depth=4, edge_types=["imports"])
    assert rows == []
