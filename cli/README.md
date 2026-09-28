# cartographer (CLI)

Per-project setup and local index provisioning for [Cartographer](../PROJECT_BRIEF.md).
This package is the CLI half of the project (brief Section 5.1); the plugin half
(skills, hooks, MCP servers) is separate, later work and is not included here.

## Install

```bash
pip install -e ".[embeddings]"
```

or, once this repo has a remote:

```bash
pip install "git+https://<host>/<org>/<repo>.git#subdirectory=cli"
```

The `embeddings` extra pulls in `fastembed` for semantic (`recall`) queries against
the local vector index. Without it, `init`, `detect`, `stack add`, `promote`, and
`doctor` all work; `recall` falls back to knowledge-graph-only results.

## Commands

| Command | What it does |
|---|---|
| `cartographer detect` | Read-only report of existing `.claude` config and what `init` would create vs. merge. |
| `cartographer init` | Scaffolds the cross-stack baseline, applies `--stacks`, provisions the local index (LanceDB + Kuzu), writes `cartographer.toml`, registers the project. Idempotent. |
| `cartographer stack add <name>` | Applies one bundled standards pack (`cross-stack`, `python`, `react`) into `.claude/standards/`. |
| `cartographer promote` | No-op in local-only topology. In central topology, reports that the central backend driver is Phase 2 work, not yet implemented. |
| `cartographer recall <query>` | Debugging aid: queries the local KG (and VDB, if `embeddings` is installed) for the current project, enforcing the tenant isolation check. |
| `cartographer doctor` | Validates config, confirms the local index opens, reports plugin wiring status. |

## What's real here, and what isn't

This CLI provisions and queries **local** state only. It does not implement:

- Central/global backends (Qdrant, Neo4j, etc.) -- Phase 2, per `PROJECT_BRIEF.md`
  Section 11. `promote` and `doctor` say so explicitly rather than faking success.
- Hooks (ingestion, preload, retrieval) and MCP servers -- the runtime bundle
  (`cli/src/cartographer/runtime/`) ships the scripts, but the hook and MCP logic
  they invoke is stubbed (Phase 1). `init` writes the config entries; they do nothing
  useful yet.
- Archaeology / spec ingestion -- that is the bundled `archaeology` skill, which
  `init` copies to `.claude/skills/`. The skill logic itself is a stub for Phase 1.

## Known limitations / open questions inherited from the brief

- Registry location defaults to `~/.cartographer/registry.json` (per-user-home). This
  is a working default, not a resolved decision -- see open question #5 in
  `PROJECT_BRIEF.md` Section 14.
- Promotion trigger and central backend choice are unresolved (open question #2 and
  Section 13); nothing here assumes an answer.
