"""SessionStart hook: preload context from the local index."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    workspace = Path(os.environ.get("CARTO_WORKSPACE", ".")).resolve()

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
            query_text = "project overview recent changes architecture decisions"
            embedding = list(next(embedder.embed([query_text])))
        except ImportError:
            sys.exit(0)

        hits = vdb_driver.query(vdb_path, scope="local", embedding=embedding, k=cfg.retrieval.top_k)
        if not hits:
            sys.exit(0)

        budget = cfg.retrieval.preload_tokens * 4
        lines = [
            "--- Cartographer knowledge context (session start) ---",
            f"Project: {cfg.project.name} ({cfg.project.id})",
            "",
        ]
        chars_used = sum(len(l) for l in lines)

        for hit in hits:
            entry = f"[{hit.get('artifact_type', '')}] {hit.get('path', '')}\n{hit.get('text', '')}\n"
            if chars_used + len(entry) > budget:
                break
            lines.append(entry)
            chars_used += len(entry)

        lines.append("--- end Cartographer context ---")
        print("\n".join(lines))

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
