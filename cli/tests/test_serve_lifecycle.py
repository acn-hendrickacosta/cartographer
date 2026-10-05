"""Phase 3.2.1: serve process lifecycle — PID file, startup collision, and
child supervision (restart-once-then-crash-loop-detection).

Real subprocess.Popen objects are used throughout (spawning cheap `python -c`
one-liners, never the real heavyweight vdb/kg servers) so the supervision loop
is exercised against real process exit codes and real timing, not mocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from cartographer.commands import serve as serve_cmd
from cartographer.runtime import serve_state


# ---------------------------------------------------------------------------
# serve_state: PID file read/write/validate
# ---------------------------------------------------------------------------

def test_pid_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: tmp_path / "serve.pid")
    state = serve_state.ServeState(
        pid=111, vdb_pid=222, kg_pid=333, vdb_port=4010, kg_port=4011,
        started_at="2026-01-01T00:00:00+00:00",
    )
    serve_state.write_pid_file(state)
    loaded = serve_state.read_pid_file()
    assert loaded == state


def test_read_pid_file_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: tmp_path / "serve.pid")
    assert serve_state.read_pid_file() is None


def test_read_pid_file_malformed_returns_none(tmp_path, monkeypatch):
    path = tmp_path / "serve.pid"
    path.write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: path)
    assert serve_state.read_pid_file() is None


def test_remove_pid_file_missing_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: tmp_path / "serve.pid")
    serve_state.remove_pid_file()  # must not raise


# ---------------------------------------------------------------------------
# is_alive: distinguish a live PID from a stale one
# ---------------------------------------------------------------------------

def test_is_alive_true_for_running_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        assert serve_state.is_alive(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()


def test_is_alive_false_for_exited_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert serve_state.is_alive(proc.pid) is False


# ---------------------------------------------------------------------------
# current_running_state: cleans up a stale PID file automatically
# ---------------------------------------------------------------------------

def test_current_running_state_cleans_up_stale_pid_file(tmp_path, monkeypatch):
    pid_path = tmp_path / "serve.pid"
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: pid_path)

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()  # already dead

    serve_state.write_pid_file(serve_state.ServeState(
        pid=proc.pid, vdb_pid=proc.pid, kg_pid=proc.pid,
        vdb_port=4010, kg_port=4011, started_at="2026-01-01T00:00:00+00:00",
    ))

    assert serve_state.current_running_state() is None
    assert not pid_path.exists()


def test_current_running_state_returns_state_for_live_process(tmp_path, monkeypatch):
    pid_path = tmp_path / "serve.pid"
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: pid_path)

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        serve_state.write_pid_file(serve_state.ServeState(
            pid=proc.pid, vdb_pid=proc.pid, kg_pid=proc.pid,
            vdb_port=4010, kg_port=4011, started_at="2026-01-01T00:00:00+00:00",
        ))
        state = serve_state.current_running_state()
        assert state is not None
        assert state.pid == proc.pid
    finally:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Startup collision check (serve.main's own logic, exercised directly)
# ---------------------------------------------------------------------------

def test_startup_blocked_by_live_healthy_pid_file(monkeypatch, capsys):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        state = serve_state.ServeState(
            pid=proc.pid, vdb_pid=proc.pid, kg_pid=proc.pid,
            vdb_port=4010, kg_port=4011, started_at="2026-01-01T00:00:00+00:00",
        )
        monkeypatch.setattr(serve_state, "read_pid_file", lambda: state)
        monkeypatch.setattr(serve_state, "is_alive", lambda pid: True)
        monkeypatch.setattr(serve_state, "is_healthy", lambda s: True)

        from typer.testing import CliRunner
        import typer
        app = typer.Typer()
        app.add_typer(serve_cmd.app, name="serve")
        result = CliRunner().invoke(app, ["serve"])

        assert result.exit_code == 1
        assert "already running" in result.output
    finally:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# supervise(): restart-once-then-crash-loop-detection, against real subprocesses
# ---------------------------------------------------------------------------

def _spawn_short_lived(exit_code: int = 1) -> subprocess.Popen:
    """A process that exits almost immediately with the given code."""
    return subprocess.Popen([sys.executable, "-c", f"import sys; sys.exit({exit_code})"])


def _spawn_long_lived() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def test_supervise_restarts_once_on_single_failure():
    """A child that fails once, then a replacement that stays up, is not a crash loop."""
    long_lived = _spawn_long_lived()
    short_lived = _spawn_short_lived()
    procs = [long_lived, short_lived]
    restart_calls = {"count": 0}

    def _restart_short() -> subprocess.Popen:
        restart_calls["count"] += 1
        return _spawn_long_lived()  # the "fixed" replacement stays up

    stop_event = threading.Event()
    restarts_seen = []

    def _on_restart(current_procs):
        restarts_seen.append(list(current_procs))
        stop_event.set()  # stop the loop right after the restart we're testing

    class _Console:
        def print(self, *a, **k):
            pass

    try:
        crash_looped = serve_cmd.supervise(
            procs,
            role_names=["long", "short"],
            restart_fns=[lambda: long_lived, _restart_short],
            stop_event=stop_event,
            on_restart=_on_restart,
            console=_Console(),
            poll_interval=0.1,
            restart_backoff=0.1,
            crash_loop_window=1.0,
        )
        assert crash_looped is False
        assert restart_calls["count"] == 1
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()


def test_supervise_detects_crash_loop():
    """A child that keeps failing immediately after restart is a crash loop."""
    long_lived = _spawn_long_lived()
    first_failure = _spawn_short_lived(exit_code=3)
    procs = [long_lived, first_failure]

    def _restart_always_fails() -> subprocess.Popen:
        return _spawn_short_lived(exit_code=3)

    stop_event = threading.Event()

    class _Console:
        def print(self, *a, **k):
            pass

    try:
        crash_looped = serve_cmd.supervise(
            procs,
            role_names=["long", "flaky"],
            restart_fns=[lambda: long_lived, _restart_always_fails],
            stop_event=stop_event,
            on_restart=lambda _procs: None,
            console=_Console(),
            poll_interval=0.1,
            restart_backoff=0.2,
            crash_loop_window=5.0,
        )
        assert crash_looped is True
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()


def test_supervise_stops_cleanly_on_stop_event():
    long_lived_a = _spawn_long_lived()
    long_lived_b = _spawn_long_lived()
    procs = [long_lived_a, long_lived_b]
    stop_event = threading.Event()

    class _Console:
        def print(self, *a, **k):
            pass

    def _stop_soon():
        time.sleep(0.3)
        stop_event.set()

    threading.Thread(target=_stop_soon, daemon=True).start()

    try:
        crash_looped = serve_cmd.supervise(
            procs,
            role_names=["a", "b"],
            restart_fns=[lambda: long_lived_a, lambda: long_lived_b],
            stop_event=stop_event,
            on_restart=lambda _procs: None,
            console=_Console(),
            poll_interval=0.1,
            restart_backoff=0.1,
            crash_loop_window=1.0,
        )
        assert crash_looped is False
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()


# ---------------------------------------------------------------------------
# cartographer serve stop / status: idempotent when nothing is running
# ---------------------------------------------------------------------------

def test_stop_when_not_running_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: tmp_path / "serve.pid")

    from typer.testing import CliRunner
    result = CliRunner().invoke(serve_cmd.app, ["stop"])
    assert result.exit_code == 0
    assert "not running" in result.output


def test_status_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_state, "pid_file_path", lambda: tmp_path / "serve.pid")

    from typer.testing import CliRunner
    result = CliRunner().invoke(serve_cmd.app, ["status"])
    assert result.exit_code == 0
    assert "not running" in result.output
