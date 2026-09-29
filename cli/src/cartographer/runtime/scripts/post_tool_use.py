"""PostToolUse hook: enqueue changed files in the dirty queue.

Called after every Write/Edit/MultiEdit tool use. Reads the tool result JSON
from stdin, extracts the affected file path, and appends it to the project's
dirty queue (.cartographer/local/dirty_queue.json).

Observe-only: does NOT embed or write to VDB/KG — that is the Stop hook's job.
"""

from __future__ import annotations

import json
import sys

from cartographer.runtime.scripts import resolve_workspace

QUEUE_FILENAME = ".cartographer/local/dirty_queue.json"


def main() -> None:
    workspace = resolve_workspace()
    queue_path = workspace / QUEUE_FILENAME
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    file_path = _extract_path(payload)
    if not file_path:
        sys.exit(0)

    if queue_path.exists():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            if not isinstance(queue, list):
                queue = []
        except Exception:
            queue = []
    else:
        queue = []

    if file_path not in queue:
        queue.append(file_path)

    queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    sys.exit(0)


def _extract_path(payload: dict) -> str | None:
    for key in ("path", "file_path", "filename"):
        if key in payload and isinstance(payload[key], str):
            return payload[key]
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        for key in ("path", "file_path"):
            if key in tool_input and isinstance(tool_input[key], str):
                return tool_input[key]
    return None


if __name__ == "__main__":
    main()
