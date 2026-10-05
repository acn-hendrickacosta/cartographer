"""UserPromptSubmit hook: retrieve context relevant to the current prompt."""

from __future__ import annotations

import json
import sys

from cartographer.runtime.scripts import resolve_workspace


def main() -> None:
    workspace = resolve_workspace()

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

        local_hits = vdb_driver.query(vdb_path, scope="local", embedding=embedding, k=cfg.retrieval.top_k)

        # Central topology: also query global scope; local results shadow global by artifact path
        global_hits: list[dict] = []
        central_vdb_handle = None
        if cfg.topology.mode == "central":
            try:
                from cartographer import config as _config_mod
                from cartographer.indexing.central import get_central_vdb
                override = _config_mod.load_local_override(workspace)
                central_vdb = get_central_vdb(cfg, override)
                central_vdb_handle = central_vdb
                global_hits = central_vdb.query(cfg.project.id, embedding=embedding, k=cfg.retrieval.top_k)
                for h in global_hits:
                    h["origin"] = "global"
            except Exception:
                pass

        local_paths = {h.get("path") for h in local_hits}
        merged = list(local_hits) + [h for h in global_hits if h.get("path") not in local_paths]

        if not merged:
            sys.exit(0)

        conflict_notices: list[str] = []
        if cfg.retrieval.conflict_notice:
            from cartographer.conflict import detect_conflicts
            conflict_notices = detect_conflicts(local_hits, central_vdb_handle, cfg.project.id, cfg.retrieval.conflict_threshold_seconds)

        budget = cfg.retrieval.per_turn_tokens * 4
        lines = ["--- Cartographer recall context ---", ""]
        chars_used = sum(len(l) for l in lines)

        for notice in conflict_notices:
            entry = notice + "\n"
            if chars_used + len(entry) > budget:
                break
            lines.append(entry)
            chars_used += len(entry)

        for hit in merged:
            origin = hit.get("origin", "local")
            entry = f"[{hit.get('artifact_type', '')}|{origin}] {hit.get('path', '')}\n{hit.get('text', '')}\n"
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
