"""Tests for the background filesystem watcher (cartographer serve's --watch)."""

import time
from pathlib import Path

from cartographer.runtime.watcher import DirtyTracker


def test_dirty_tracker_not_ready_before_debounce_elapses():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    assert tracker.ready_batches(debounce=10.0) == []


def test_dirty_tracker_ready_after_debounce_elapses():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", {Path("/fake/a.py")})]


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
    # Still within 0.05s of the *second* touch, so not ready at a 0.2s debounce
    assert tracker.ready_batches(debounce=0.2) == []


def test_dirty_tracker_batches_multiple_paths_for_same_project():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.mark("proj_a", Path("/fake/b.py"))
    batches = tracker.ready_batches(debounce=0.0)
    assert batches == [("proj_a", {Path("/fake/a.py"), Path("/fake/b.py")})]


def test_dirty_tracker_keeps_projects_independent():
    tracker = DirtyTracker()
    tracker.mark("proj_a", Path("/fake/a.py"))
    tracker.mark("proj_b", Path("/fake/c.py"))
    batches = dict(tracker.ready_batches(debounce=0.0))
    assert batches == {"proj_a": {Path("/fake/a.py")}, "proj_b": {Path("/fake/c.py")}}
