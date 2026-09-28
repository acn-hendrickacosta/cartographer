# Cartographer

Cartographer gives any Claude Code project a persistent knowledge layer: a local knowledge graph and vector index that are kept current automatically as code and specs change, and that Claude consults automatically while working. It ships with cross-stack development standards and installs in one command into a new or existing project.

---

## The problem it solves

Claude Code loses context between sessions. It re-reads files it has already understood, forgets decisions from earlier sessions, and has no durable model of how a codebase and its specifications relate. Asking Claude to "remember" something is not a guarantee -- reliability for always-on behavior requires deterministic hooks, not prompting.

Cartographer wires those hooks. Knowledge is captured on every edit and injected at every session start and every prompt turn, without the developer or Claude having to ask.

---

## How it works

Three layers:

1. **CLI** (`cartographer`) -- sets up the workspace, provisions the local index, and manages standards packs. Run once at project start; idempotent after that.
2. **Plugin** -- skills and hooks that travel with the project. Hooks ingest changes automatically; skills handle deliberate, judgment-heavy operations like indexing an existing codebase or cross-project recall.
3. **State layer** -- a local vector database (LanceDB) and knowledge graph (Kuzu), provisioned per project, with an opt-in upgrade path to a shared central backend for multi-developer teams.

---

## Quick start

### Install the CLI

```bash
pip install "cartographer-cli[embed]"
```

### Initialize a project

```bash
cd my-project
cartographer init --stack python
```

This detects and merges any existing Claude Code configuration, writes the cross-stack and Python standards into `.claude/standards/`, provisions the local VDB and KG, and wires the plugin hooks. Nothing is overwritten without a backup.

### Seed existing documentation

```bash
cartographer seed docs/
```

Ingests a documentation directory into the local index immediately. Supported formats: `.md`, `.rst`, `.txt`, `.adoc`, `.docx`, `.pptx`, `.pdf`.

### Index an existing codebase

Open a Claude Code session in the project and run:

```
/archaeology
```

This bootstraps the knowledge base from the existing codebase and documentation in one pass. After it completes, the ingest hooks maintain the index incrementally on every edit.

### Browse the knowledge layer

```bash
cartographer ui
```

Opens a local web interface at `http://localhost:7341` with four views: semantic search over the VDB, a graph explorer for KG nodes and edges, a registry browser, and index stats. Useful for verifying that the knowledge layer is populated correctly after `init` or `seed`.

### Verify the setup

```bash
cartographer doctor
```

Reports the health of the config, local backends, and plugin wiring.

---

## Repository structure

```
cartographer/
  cli/                        Python CLI package (pip-installable)
    src/cartographer/
      ui/                     Local knowledge browser (cartographer ui command)
  cartographer-plugin/        Claude Code plugin (skills, hooks, MCP servers)
  standards/                  Cross-stack baseline and per-stack packs
  standards-webapp/           Standards web app: SME authoring and publishing (deferred phase)
  docs/                       Full documentation set
  cartographer.example.toml   Annotated example config
```

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System layers, topologies, AWS reference deployment |
| [docs/APPLICATION_ARCHITECTURE.md](docs/APPLICATION_ARCHITECTURE.md) | CLI command flows, web app screen flows, hook runtime flows |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | VDB, KG, and registry schemas; artifact identity; promotion mechanics |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every config knob, the two-file model, environment variable overrides |
| [docs/SECURITY_AND_ISOLATION.md](docs/SECURITY_AND_ISOLATION.md) | Tenant isolation, data egress rules, secret handling |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases, scope, and exit criteria |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Decisions still open; what blocks each phase |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to add a stack pack or contribute to the project |
| [docs/phases/phase-1-mvp-local.md](docs/phases/phase-1-mvp-local.md) | Phase 1 implementation plan: scope, build order, exit criteria, test approach |
| [docs/phases/phase-2-central.md](docs/phases/phase-2-central.md) | Phase 2 implementation plan: central backends, promotion, multi-developer |
| [docs/phases/phase-3-sync-lifecycle.md](docs/phases/phase-3-sync-lifecycle.md) | Phase 3 implementation plan: deletions, renames, conflict resolution |
| [docs/phases/standards-registry.md](docs/phases/standards-registry.md) | Standards Registry and web app implementation plan |
| [docs/components/cli.md](docs/components/cli.md) | CLI component spec: all commands including `cartographer ui`, inputs, outputs, failure modes |
| [docs/components/standards-webapp.md](docs/components/standards-webapp.md) | Standards web app spec: roles, lifecycle, screen inventory, AWS infrastructure, API surface |
| [docs/components/hooks.md](docs/components/hooks.md) | Hook contracts, portability rules, failure handling |
| [docs/components/mcp-servers.md](docs/components/mcp-servers.md) | MCP server definitions, driver interface, authorization matrix |
| [docs/components/skills.md](docs/components/skills.md) | Archaeology and recall skill specs |
| [docs/contracts/vdb-tools.md](docs/contracts/vdb-tools.md) | VDB MCP tool contracts |
| [docs/contracts/kg-tools.md](docs/contracts/kg-tools.md) | KG MCP tool contracts |

---

## Configuration

Copy `cartographer.example.toml` to `cartographer.toml` in the project root and edit as needed. The example file is fully annotated.

Per-developer secrets and endpoint overrides go in `.cartographer.local.toml`, which is gitignored. Never put API keys in `cartographer.toml`.

For the full configuration reference, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Topologies

| Topology | When | Setup |
|---|---|---|
| Local only (default) | Solo developer or small team not ready for shared infra | `cartographer init` -- no extra config needed |
| Central, opt-in | Multi-developer project wanting shared knowledge after merges | Set `topology.mode = "central"` and configure central VDB and KG endpoints in `.cartographer.local.toml` |

In local-only topology, the VDB and KG run entirely on-disk on the developer's machine (LanceDB and Kuzu). No service, no network, no cloud account required.

---

## Standards packs

Cartographer ships three packs:

| Pack | Contents |
|---|---|
| `cross-stack` | Always applied. Git hygiene, spec-driven workflow, review standards, security baseline, Claude Code usage norms. |
| `python` | Python-specific standards. Applied with `--stack python` at init or `cartographer stack add python`. |
| `react` | React-specific standards. Applied with `--stack react` at init or `cartographer stack add react`. |

To add a new stack pack, see [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## Multi-developer setup

For teams using the central topology:

1. Provision a central VDB backend (pgvector on Aurora, Qdrant, or any supported driver) and a central KG backend (Neo4j, Neptune, or any supported driver).
2. Issue each developer their own API key for the central backends.
3. Each developer sets `topology.mode = "central"` in `cartographer.toml` and their API keys in `.cartographer.local.toml`.
4. Configure the promotion trigger. The recommended path is a CI step that runs `cartographer promote` on merge to main.

After a branch merges and promotion runs, all developers see the merged knowledge in their next session.

---

## Known limitations

| Limitation | Detail |
|---|---|
| Hooks do not fire in Claude Code Cowork Desktop | Cowork restricts project-scope settings. The always-on ingest, preload, and retrieve hooks are not triggered. Skills and MCP servers still work. Run `cartographer seed` manually and use `/recall` explicitly when working in Cowork. |
| Binary document extraction requires a Claude Code session | `.docx`, `.pptx`, and `.pdf` files are extracted using local Claude via MCP. Running `cartographer seed` from a plain terminal outside a Claude Code session skips binary files with a warning. |
| `cartographer ui` graph view requires internet access for D3.js | The graph view loads D3.js from CDN. In offline environments it degrades to a node list. The search, registry, and stats views work fully offline. |
| Deletions and renames are not reconciled across the promotion boundary | Stale artifacts remain in the global index until Phase 3. |

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## License

Internal use. Open to contribution -- see license file for details.
