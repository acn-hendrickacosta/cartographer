"""Background filesystem watcher — keeps every registered project's local
index current automatically, independent of Claude Code hooks entirely.

Runs inside `cartographer serve` (see commands/serve.py) rather than as its
own command: `cartographer serve` is already the one long-running process a
user must start for MCP to work over HTTP (stdio MCP is blocked in many
enterprise deployments), so piggybacking here adds zero extra process to
remember to run. It also catches changes Claude Code hooks structurally never
could — hooks only fire on Claude Code's own tool calls, so a `git pull`, a
branch switch, or an edit from another tool never re-ingests via hooks. A
filesystem watcher catches all of these the same way it catches Claude's own edits.

Enterprise note: some Claude Code deployments set `allowManagedHooksOnly` in
managed settings, which silently blocks any hook a project's own
.claude/settings.json defines (including cartographer's own ingest hooks, see
commands/init.py's _hooks()). This watcher does not use Claude Code hooks at
all, so it is unaffected by that policy.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from cartographer import config as config_mod, registry
from cartographer.ingestion.pipeline import ingest_paths
from cartographer.ingestion.text_extractor import is_ingestible_path

DEBOUNCE_SECONDS = 3.0
REGISTRY_RESCAN_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.5


class DirtyTracker:
    """Thread-safe per-project set of changed and deleted paths with a last-touched clock.

    Debouncing (rather than ingesting on every single event) matters because
    editors commonly fire several write events per save, and a large find-and-
    replace or `git checkout` can touch hundreds of files within milliseconds.

    Deleted paths are tracked separately from dirty paths so _flush_ready can
    call delete_by_path before ingesting new content — critical for renames,
    where the old path must be removed before the new path is ingested.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dirty: dict[str, set[Path]] = {}
        self._deleted: dict[str, set[Path]] = {}
        self._last_touch: dict[str, float] = {}

    def mark(self, project_id: str, path: Path) -> None:
        with self._lock:
            self._dirty.setdefault(project_id, set()).add(path)
            self._last_touch[project_id] = time.monotonic()

    def mark_deleted(self, project_id: str, path: Path) -> None:
        with self._lock:
            self._deleted.setdefault(project_id, set()).add(path)
            self._last_touch[project_id] = time.monotonic()

    def ready_batches(self, debounce: float) -> list[tuple[str, set[Path], set[Path]]]:
        """Pop and return (project_id, dirty_paths, deleted_paths) for every project
        that has been idle for at least `debounce` seconds since its last change."""
        now = time.monotonic()
        ready: list[tuple[str, set[Path], set[Path]]] = []
        with self._lock:
            all_projects = set(self._dirty) | set(self._deleted)
            for project_id in list(all_projects):
                if now - self._last_touch.get(project_id, 0.0) >= debounce:
                    dirty = self._dirty.pop(project_id, set())
                    deleted = self._deleted.pop(project_id, set())
                    self._last_touch.pop(project_id, None)
                    ready.append((project_id, dirty, deleted))
        return ready


class _ProjectHandler(FileSystemEventHandler):
    def __init__(self, project_id: str, tracker: DirtyTracker) -> None:
        self._project_id = project_id
        self._tracker = tracker

    def _consider(self, raw_path: str) -> None:
        p = Path(raw_path)
        if is_ingestible_path(p) and p.is_file():
            self._tracker.mark(self._project_id, p)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._tracker.mark_deleted(self._project_id, Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._tracker.mark_deleted(self._project_id, Path(event.src_path))
            self._consider(event.dest_path)


def _sync_watches(observer: Observer, tracker: DirtyTracker, watched: dict[str, object]) -> None:
    """Reconcile watchdog's active watches against the current registry —
    projects registered or removed while `serve` is already running are picked
    up within one rescan interval, no restart needed."""
    projects = {p.project_id: p for p in registry.list_projects()}

    for project_id in list(watched.keys()):
        if project_id not in projects:
            observer.unschedule(watched.pop(project_id))

    for project_id, record in projects.items():
        if project_id in watched:
            continue
        workspace = Path(record.location)
        if not workspace.is_dir() or not config_mod.config_exists(workspace):
            continue
        handler = _ProjectHandler(project_id, tracker)
        watched[project_id] = observer.schedule(handler, str(workspace), recursive=True)


def _flush_ready(tracker: DirtyTracker, embedder_holder: list) -> None:
    from cartographer.indexing import vdb, kg

    for project_id, dirty_paths, deleted_paths in tracker.ready_batches(DEBOUNCE_SECONDS):
        record = registry.get_project(project_id)
        if record is None:
            continue
        workspace = Path(record.location)
        try:
            cfg = config_mod.load_config(workspace)
        except Exception:
            continue

        local_dir = workspace / ".cartographer" / "local"

        # Process deletions before ingesting so a rename (delete + add) never
        # leaves both old and new paths in the index at the same time.
        for path in deleted_paths:
            try:
                vdb.delete_by_path(local_dir / "vdb.lance", str(path))
                kg.delete_by_path(local_dir / "kg.kuzu", str(path))
            except Exception:
                pass

        existing_dirty = [p for p in dirty_paths if p.exists()]
        if not existing_dirty:
            continue

        if embedder_holder[0] is None:
            from cartographer.ingestion.embedder import get_embedder
            embedder_holder[0] = get_embedder()

        try:
            ingest_paths(
                existing_dirty,
                project_id=cfg.project.id,
                workspace_root=workspace,
                vdb_path=local_dir / "vdb.lance",
                kg_path=local_dir / "kg.kuzu",
                scope="local",
                embedder=embedder_holder[0],
            )
        except Exception:
            # Best-effort background watcher: one project's ingestion failure
            # must never take down the shared `serve` process other projects
            # depend on for MCP.
            pass


def watch_projects(stop_event: threading.Event | None = None) -> None:
    """Watch every registered project's workspace and flush changed files into
    its local VDB/KG after a short idle debounce. Runs until `stop_event` is set."""
    stop_event = stop_event or threading.Event()
    tracker = DirtyTracker()
    watched: dict[str, object] = {}
    embedder_holder: list = [None]  # lazy: avoid the embedder's startup cost until something actually changes

    observer = Observer()
    observer.start()
    try:
        last_rescan = 0.0
        while not stop_event.is_set():
            now = time.monotonic()
            if now - last_rescan >= REGISTRY_RESCAN_SECONDS:
                _sync_watches(observer, tracker, watched)
                last_rescan = now

            _flush_ready(tracker, embedder_holder)
            stop_event.wait(POLL_INTERVAL_SECONDS)
    finally:
        observer.stop()
        observer.join(timeout=5)
