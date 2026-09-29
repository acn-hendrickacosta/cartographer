"""SessionStart hook: preload context from the local index."""

from __future__ import annotations

import sys

from cartographer.runtime.scripts import resolve_workspace


def main() -> None:
    workspace = resolve_workspace()

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

        local_hits = vdb_driver.query(vdb_path, scope="local", embedding=embedding, k=cfg.retrieval.top_k)

        # Central topology: also query global scope; local results shadow global by artifact id
        global_hits: list[dict] = []
        if cfg.topology.mode == "central":
            try:
                from cartographer import config as _config_mod
                from cartographer.indexing.central import get_central_vdb
                override = _config_mod.load_local_override(workspace)
                central_vdb = get_central_vdb(cfg, override)
                global_hits = central_vdb.query(cfg.project.id, embedding=embedding, k=cfg.retrieval.top_k)
                for h in global_hits:
                    h["origin"] = "global"
            except Exception:
                pass

        # Merge: local shadows global for same artifact path
        local_paths = {h.get("path") for h in local_hits}
        merged = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]

        if not merged:
            sys.exit(0)

        budget = cfg.retrieval.preload_tokens * 4
        lines = [
            "--- Cartographer knowledge context (session start) ---",
            f"Project: {cfg.project.name} ({cfg.project.id})",
            "",
        ]
        chars_used = sum(len(l) for l in lines)

        for hit in merged:
            origin = hit.get("origin", "local")
            entry = f"[{hit.get('artifact_type', '')}|{origin}] {hit.get('path', '')}\n{hit.get('text', '')}\n"
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
