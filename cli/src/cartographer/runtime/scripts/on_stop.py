"""Stop hook: flush the dirty queue into the local VDB and KG."""

from __future__ import annotations

import os
import sys
from pathlib import Path

MAX_FILES_PER_FLUSH = 20
QUEUE_FILENAME = ".cartographer/local/dirty_queue.json"


def main() -> None:
    import json

    workspace = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()
    queue_path = workspace / QUEUE_FILENAME

    if not queue_path.exists():
        sys.exit(0)

    try:
        queue: list[str] = json.loads(queue_path.read_text(encoding="utf-8"))
        if not isinstance(queue, list):
            queue = []
    except Exception:
        queue = []

    if not queue:
        sys.exit(0)

    seen: set[str] = set()
    unique: list[str] = []
    for p in queue:
        if p not in seen:
            unique.append(p)
            seen.add(p)

    batch = unique[:MAX_FILES_PER_FLUSH]
    remaining = unique[MAX_FILES_PER_FLUSH:]

    try:
        from cartographer import config as config_mod
        from cartographer.ingestion.embedder import get_embedder
        from cartographer.ingestion.pipeline import ingest_paths

        if not config_mod.config_exists(workspace):
            sys.exit(0)

        cfg = config_mod.load_config(workspace)
        local_dir = workspace / ".cartographer" / "local"

        paths = [Path(p) for p in batch if Path(p).exists()]
        if paths:
            embedder = get_embedder()
            ingest_paths(
                paths,
                project_id=cfg.project.id,
                workspace_root=workspace,
                vdb_path=local_dir / "vdb.lance",
                kg_path=local_dir / "kg.kuzu",
                scope="local",
                embedder=embedder,
            )
    except Exception:
        remaining = unique

    queue_path.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
