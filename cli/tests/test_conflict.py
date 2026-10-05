"""Phase 3.4: conflict detection unit tests.

detect_conflicts looks up each local hit's path directly via
central_vdb.query_by_path — not via incidental overlap with a top-k
similarity result list — so these tests exercise that contract directly
against a mocked driver.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cartographer.conflict import _is_conflict, detect_conflicts


# ---------------------------------------------------------------------------
# _is_conflict
# ---------------------------------------------------------------------------

def test_is_conflict_true_when_timestamps_differ_and_threshold_zero():
    assert _is_conflict("2026-01-01T00:00:00", "2026-01-01T00:00:01", 0) is True


def test_is_conflict_false_when_timestamps_identical():
    assert _is_conflict("2026-01-01T00:00:00", "2026-01-01T00:00:00", 0) is False


def test_is_conflict_false_when_local_timestamp_absent():
    assert _is_conflict("", "2026-01-01T00:00:00", 0) is False


def test_is_conflict_false_when_global_timestamp_absent():
    assert _is_conflict("2026-01-01T00:00:00", "", 0) is False


def test_is_conflict_respects_threshold_below():
    # 30 seconds apart, threshold 60 — not a conflict
    assert _is_conflict("2026-01-01T00:00:00", "2026-01-01T00:00:30", 60) is False


def test_is_conflict_respects_threshold_above():
    # 90 seconds apart, threshold 60 — is a conflict
    assert _is_conflict("2026-01-01T00:00:00", "2026-01-01T00:01:30", 60) is True


def test_is_conflict_false_on_unparseable_timestamp():
    assert _is_conflict("not-a-timestamp", "2026-01-01T00:00:00", 0) is False


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------

def test_detect_conflicts_returns_empty_when_central_vdb_is_none():
    local_hits = [{"path": "src/a.py", "updated_at": "2026-01-01T00:00:00"}]
    assert detect_conflicts(local_hits, None, "proj", 0) == []


def test_detect_conflicts_finds_divergent_path_via_query_by_path():
    central_vdb = MagicMock()
    central_vdb.query_by_path.return_value = {"path": "src/a.py", "updated_at": "2026-01-01T09:00:00"}
    local_hits = [{"path": "src/a.py", "updated_at": "2026-01-01T14:00:00"}]

    notices = detect_conflicts(local_hits, central_vdb, "proj", 0)

    central_vdb.query_by_path.assert_called_once_with("proj", "src/a.py")
    assert len(notices) == 1
    assert "src/a.py" in notices[0]
    assert "2026-01-01T14:00:00" in notices[0]
    assert "2026-01-01T09:00:00" in notices[0]


def test_detect_conflicts_no_notice_when_global_counterpart_absent():
    """A local hit whose path was never promoted (query_by_path returns None)
    is not a conflict — there is nothing to diverge from."""
    central_vdb = MagicMock()
    central_vdb.query_by_path.return_value = None
    local_hits = [{"path": "src/new_local_only.py", "updated_at": "2026-01-01T14:00:00"}]

    assert detect_conflicts(local_hits, central_vdb, "proj", 0) == []


def test_detect_conflicts_no_notice_when_timestamps_match():
    central_vdb = MagicMock()
    central_vdb.query_by_path.return_value = {"path": "src/a.py", "updated_at": "2026-01-01T14:00:00"}
    local_hits = [{"path": "src/a.py", "updated_at": "2026-01-01T14:00:00"}]

    assert detect_conflicts(local_hits, central_vdb, "proj", 0) == []


def test_detect_conflicts_fires_regardless_of_similarity_ranking():
    """The whole point of the fix: detect_conflicts must not depend on the
    global hit having ranked in any top-k similarity list. A MagicMock with
    no .query() configured at all (only .query_by_path) proves this."""
    central_vdb = MagicMock(spec=["query_by_path"])
    central_vdb.query_by_path.return_value = {"path": "src/drifted.py", "updated_at": "2020-01-01T00:00:00"}
    local_hits = [{"path": "src/drifted.py", "updated_at": "2026-01-01T00:00:00"}]

    notices = detect_conflicts(local_hits, central_vdb, "proj", 0)
    assert len(notices) == 1


def test_detect_conflicts_one_failed_lookup_does_not_block_others():
    central_vdb = MagicMock()

    def _side_effect(project_id, path):
        if path == "src/broken.py":
            raise Exception("connection reset")
        return {"path": path, "updated_at": "2020-01-01T00:00:00"}

    central_vdb.query_by_path.side_effect = _side_effect
    local_hits = [
        {"path": "src/broken.py", "updated_at": "2026-01-01T00:00:00"},
        {"path": "src/fine.py", "updated_at": "2026-01-01T00:00:00"},
    ]

    notices = detect_conflicts(local_hits, central_vdb, "proj", 0)
    assert len(notices) == 1
    assert "src/fine.py" in notices[0]


def test_detect_conflicts_skips_hits_without_path():
    central_vdb = MagicMock()
    local_hits = [{"updated_at": "2026-01-01T00:00:00"}]
    assert detect_conflicts(local_hits, central_vdb, "proj", 0) == []
    central_vdb.query_by_path.assert_not_called()
