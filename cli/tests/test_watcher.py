"""Tests for the background filesystem watcher (cartographer serve's --watch)."""

import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from cartographer.runtime.watcher import DirtyTracker, _ProjectHandler


# ---------------------------------------------------------------------------
# DirtyTracker — dirty path tracking (existing behaviour)
# ---------------------------------------------------------------------------

def test_dirty_tracker_not_ready_before_debounce_elapses():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    assert tracker.ready_batches(debounce=10.0) == []


def test_dirty_tracker_ready_after_debounce_elapses():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", {Path("/fake/a.py")}, set())]


def test_dirty_tracker_pops_ready_projects_only_once():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.ready_batches(debounce=0.0)
    assert tracker.ready_batches(debounce=0.0) == []


def test_dirty_tracker_touch_resets_the_debounce_window():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    time.sleep(0.05)
    tracker.mark("proj_a", Path("/fake/b.py"))
    assert tracker.ready_batches(debounce=0.2) == []


def test_dirty_tracker_batches_multiple_paths_for_same_project():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.mark("proj_a", Path("/fake/b.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", {Path("/fake/a.py"), Path("/fake/b.py")}, set())]


def test_dirty_tracker_keeps_projects_independent():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.mark("proj_b", Path("/fake/c.py"))
    batches = {pid: (d, dl) for pid, d, dl in tracker.ready_batches(debounce=0.0)}
    assert batches == {
        "proj_a": ({Path("/fake/a.py")}, set()),
        "proj_b": ({Path("/fake/c.py")}, set()),
    }


# ---------------------------------------------------------------------------
# DirtyTracker — deleted path tracking (Phase 3.1)
# ---------------------------------------------------------------------------

def test_mark_deleted_batches_separately_from_dirty():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.mark_deleted("proj_a", Path("/fake/old.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", {Path("/fake/a.py")}, {Path("/fake/old.py")})]


def test_mark_deleted_only_no_dirty_paths():
    tracker = DirtyTracker()
    tracker.mark_deleted("proj_a", Path("/fake/gone.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", set(), {Path("/fake/gone.py")})]


def test_mark_deleted_resets_debounce():
    tracker = DirtyTracker()
    tracker.mark_deleted("proj_a", Path("/fake/gone.py"))
    # Within debounce window — should not be ready yet
    assert tracker.ready_batches(debounce=10.0) == []


def test_deleted_paths_popped_after_ready_batches():
    tracker = DirtyTracker()
    tracker.mark_deleted("proj_a", Path("/fake/gone.py"))
    tracker.ready_batches(debounce=0.0)
    assert tracker.ready_batches(debounce=0.0) == []


# ---------------------------------------------------------------------------
# _ProjectHandler — on_deleted (Phase 3.1)
# ---------------------------------------------------------------------------

def _make_event(src_path: str, dest_path: str = "", is_directory: bool = False):
    evt = MagicMock()
    evt.src_path = src_path
    evt.dest_path = dest_path
    evt.is_directory = is_directory
    return evt


def test_on_deleted_marks_path_as_deleted():
    tracker = DirtyTracker()
    handler = _ProjectHandler("proj_a", tracker)
    handler.on_deleted(_make_event("/fake/deleted.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", set(), {Path("/fake/deleted.py")})]


def test_on_deleted_ignores_directory_events():
    tracker = DirtyTracker()
    handler = _ProjectHandler("proj_a", tracker)
    handler.on_deleted(_make_event("/fake/somedir", is_directory=True))
    assert tracker.ready_batches(debounce=0.0) == []


# ---------------------------------------------------------------------------
# _ProjectHandler — on_moved (Phase 3.1 enhancement)
# ---------------------------------------------------------------------------

def test_on_moved_marks_src_deleted_and_queues_dest(tmp_path):
    dest = tmp_path / "new.py"
    dest.write_text("x = 1")

    tracker = DirtyTracker()
    handler = _ProjectHandler("proj_a", tracker)
    handler.on_moved(_make_event(str(tmp_path / "old.py"), str(dest)))

    batches = tracker.ready_batches(debounce=0.0)
    assert len(batches) == 1
    pid, dirty, deleted = batches[0]
    assert pid == "proj_a"
    assert Path(str(tmp_path / "old.py")) in deleted
    assert dest in dirty


def test_on_moved_ignores_directory_events():
    tracker = DirtyTracker()
    handler = _ProjectHandler("proj_a", tracker)
    handler.on_moved(_make_event("/fake/olddir", "/fake/newdir", is_directory=True))
    assert tracker.ready_batches(debounce=0.0) == []


# ---------------------------------------------------------------------------
# vdb.delete_by_path (Phase 3.1)
# ---------------------------------------------------------------------------

def test_vdb_delete_by_path_removes_chunks(tmp_path):
    from cartographer.indexing import vdb
    from cartographer.indexing.vdb import ChunkRecord

    db_path = tmp_path / "test.lance"
    chunk = ChunkRecord(
        id="test#0",
        project_id="proj_x",
        scope="local",
        artifact_type="code",
        path="src/target.py",
        origin="local",
        text="hello",
        embedding=[0.1] * 384,
        updated_at="2026-01-01T00:00:00Z",
    )
    vdb.upsert(db_path, "local", [chunk])
    assert len(vdb.scan(db_path, "local")) == 1

    vdb.delete_by_path(db_path, "src/target.py")
    assert vdb.scan(db_path, "local") == []


def test_vdb_delete_by_path_leaves_other_paths(tmp_path):
    from cartographer.indexing import vdb
    from cartographer.indexing.vdb import ChunkRecord

    db_path = tmp_path / "test.lance"

    def _chunk(path: str, cid: str) -> ChunkRecord:
        return ChunkRecord(
            id=cid, project_id="proj_x", scope="local", artifact_type="code",
            path=path, origin="local", text="t", embedding=[0.1] * 384,
            updated_at="2026-01-01T00:00:00Z",
        )

    vdb.upsert(db_path, "local", [_chunk("src/keep.py", "keep#0"), _chunk("src/gone.py", "gone#0")])
    vdb.delete_by_path(db_path, "src/gone.py")

    remaining = [r["path"] for r in vdb.scan(db_path, "local")]
    assert remaining == ["src/keep.py"]


def test_vdb_delete_by_path_noop_when_db_absent(tmp_path):
    from cartographer.indexing import vdb
    # Should not raise even if the db doesn't exist yet
    vdb.delete_by_path(tmp_path / "nonexistent.lance", "src/foo.py")


# ---------------------------------------------------------------------------
# kg.delete_by_path (Phase 3.1)
# ---------------------------------------------------------------------------

def test_kg_delete_by_path_removes_node(tmp_path):
    from cartographer.indexing import kg
    from cartographer.indexing.kg import Node

    kg_path = tmp_path / "test.kuzu"
    kg.ensure_namespace(kg_path)
    kg.upsert_nodes(kg_path, [Node(
        id="node-1", project_id="proj_x", scope="local",
        type="module", path="src/target.py",
    )])

    rows = kg.query(kg_path, "MATCH (a:Artifact) WHERE a.path = 'src/target.py' RETURN a.id")
    assert len(rows) == 1

    kg.delete_by_path(kg_path, "src/target.py")

    rows = kg.query(kg_path, "MATCH (a:Artifact) WHERE a.path = 'src/target.py' RETURN a.id")
    assert rows == []


def test_kg_delete_by_path_leaves_other_nodes(tmp_path):
    from cartographer.indexing import kg
    from cartographer.indexing.kg import Node

    kg_path = tmp_path / "test.kuzu"
    kg.ensure_namespace(kg_path)
    kg.upsert_nodes(kg_path, [
        Node(id="keep-1", project_id="proj_x", scope="local", type="module", path="src/keep.py"),
        Node(id="gone-1", project_id="proj_x", scope="local", type="module", path="src/gone.py"),
    ])

    kg.delete_by_path(kg_path, "src/gone.py")

    rows = kg.query(kg_path, "MATCH (a:Artifact) RETURN a.path")
    paths = [r["a.path"] for r in rows]
    assert paths == ["src/keep.py"]


def test_kg_delete_by_path_noop_when_db_absent(tmp_path):
    from cartographer.indexing import kg
    kg.delete_by_path(tmp_path / "nonexistent.kuzu", "src/foo.py")
