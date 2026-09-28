"""UserPromptSubmit hook: retrieve context relevant to the current prompt."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    workspace = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()

    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)

    prompt_text = raw
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            prompt_text = payload.get("prompt", raw)
    except Exception:
        pass

    try:
        from cartographer import config as config_mod
        from cartographer.indexing import vdb as vdb_driver

        if not config_mod.config_exists(workspace):
            sys.exit(0)

        cfg = config_mod.load_config(workspace)
        local_dir = workspace / ".cartographer" / "local"
        vdb_path = local_dir / "vdb.lance"

        if not vdb_path.exists():
            sys.exit(0)

        try:
            from fastembed import TextEmbedding
            embedder = TextEmbedding()
            embedding = list(next(embedder.embed([prompt_text[:512]])))
        except ImportError:
            sys.exit(0)

        hits = vdb_driver.query(vdb_path, scope="local", embedding=embedding, k=cfg.retrieval.top_k)
        if not hits:
            sys.exit(0)

        budget = cfg.retrieval.per_turn_tokens * 4
        lines = ["--- Cartographer recall context ---", ""]
        chars_used = sum(len(l) for l in lines)

        for hit in hits:
            entry = f"[{hit.get('artifact_type', '')}] {hit.get('path', '')}\n{hit.get('text', '')}\n"
            if chars_used + len(entry) > budget:
                break
            lines.append(entry)
            chars_used += len(entry)

        lines.append("--- end recall context ---")
        print("\n".join(lines))

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
