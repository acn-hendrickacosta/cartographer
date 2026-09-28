# Cartographer: Open Questions

This document tracks decisions that have not been made and must be resolved before or during the phase they block. Do not resolve questions silently -- record the decision here, link to the ADR if one is written, and mark the question closed.

Questions are grouped by the phase or component they block. Questions blocking Phase 1 must be resolved before implementation starts.

---

## Phase 1 blockers

These questions must be answered before the first line of implementation is written.

---

### OQ-01: Promotion trigger default

**Question:** What is the default promotion trigger for a new project -- CI step on merge, git post-merge hook, or manual command?

**Why it matters:** The default shapes what `cartographer init` sets up out of the box and what the onboarding instructions say. A wrong default means teams either never promote or over-promote.

**Options:**

| Option | Tradeoff |
|---|---|
| CI step (`ci`) | Most reliable. Requires a CI pipeline. Adds a step to the pipeline config. |
| Git post-merge hook (`post-merge-hook`) | No CI required. Runs on the developer's machine. Skipped if the developer forgets to pull. |
| Manual (`manual`) | Explicit but forgettable. Suitable for very small teams or early adopters who want full control. |

**Lean:** `ci`, with `manual` as the documented fallback for projects without CI.

**Status:** Open. Blocks `cartographer init` default config output.

---

### OQ-02: Retrieval token budgets

**Question:** What are the default values for `recall.preload_budget_tokens` (session context injection) and `recall.per_turn_budget_tokens` (per-prompt injection)?

**Why it matters:** Too low and the knowledge layer adds no value. Too high and the context window fills with recall noise, leaving less room for the actual conversation and code.

**Current defaults in config:** `preload_budget_tokens = 1500`, `per_turn_budget_tokens = 800`.

**What to validate:** Run a live session with a non-trivial codebase and measure whether the injected context is useful or noisy at these values. Adjust before publishing the defaults.

**Status:** Open. Defaults are placeholder values. Requires a real session test. Blocks Phase 1 acceptance gate.

---

### OQ-03: Spec file format and detection

**Question:** What does a spec file look like in the spec-driven workflow, and how does the ingest hook identify one?

**Why it matters:** Specs are described as higher-signal than code. The ingest hook watches them with higher priority and the KG anchors `implements_spec` edges to them. If the hook cannot reliably detect a spec file, the spec-driven part of the system does not work.

**Options:**

| Option | Tradeoff |
|---|---|
| Path convention: files under `specs/` or `spec/` | Simple. Requires teams to follow the convention. |
| Filename pattern: `*.spec.md`, `*.spec.yaml` | More flexible. Ambiguous for some naming styles. |
| Frontmatter marker: YAML frontmatter with `type: spec` | Explicit and machine-readable. Requires authors to add frontmatter. |
| Config-driven: `ingestion.spec_patterns` list | Most flexible. Requires per-project configuration. |

**Lean:** Path convention as the default (`specs/`, `spec/`), with `ingestion.spec_patterns` as the config override. Frontmatter marker as an additional signal if present.

**Status:** Open. Blocks the ingest hook's artifact type inference and the archaeology skill's traversal strategy.

---

### OQ-04: Registry location in local-only topology

**Question:** Where does the per-machine project registry live -- per-user home directory, or configurable?

**Current default in config:** `~/.cartographer/registry.db`.

**Why it matters:** A per-home-directory registry works for a single user but breaks in shared CI environments or Docker containers where the home directory is ephemeral.

**Options:**

| Option | Tradeoff |
|---|---|
| `~/.cartographer/registry.db` (per-user) | Works for local dev. Breaks in ephemeral environments. |
| Configurable via `registry.path` | Flexible. Teams using CI must configure it explicitly. |
| Inside the project directory (`.cartographer/registry.db`) | Portable with the project. Cannot support cross-project recall without a global fallback. |

**Lean:** `~/.cartographer/registry.db` as the default, configurable via `registry.path`. CI environments set `CARTO_REGISTRY_PATH` to a suitable persistent volume.

**Status:** Open. Blocks final registry design.

---

### OQ-05: Marketplace hosting

**Question:** Where is the plugin hosted for `git`-based installation? What is the URL, access model, and who owns the repository?

**Why it matters:** `cartographer init` and `cartographer detect` need to know where the plugin lives to register it in `.mcp.json`. The install URL must be stable and accessible to all developers on a project.

**What needs to be decided:**
- Internal git host vs. public GitHub.
- Whether the plugin repo is the same repo as the CLI or a separate one.
- Access control (open, org-restricted, or invite-only).
- Whether the plugin is versioned independently of the CLI.

**Status:** Open. Blocks the `.mcp.json` entry template that `cartographer init` generates.

---

### OQ-06: Standards pack versioning and pinning

**Question:** How are standards pack versions identified, and can a project pin to a specific version?

**Why it matters:** If pack versions are not pinned, a `cartographer stack add` run on two different dates can produce different results. This breaks reproducibility for teams that want stable standards.

**Options:**

| Option | Tradeoff |
|---|---|
| Semantic version (`1.4.0`) | Standard, tooling-friendly. Requires discipline in the release process. |
| Date-stamped version (`2026-09-24`) | Simple. Obvious what "latest" means. No semver semantics. |
| Git SHA of the standards repo | Maximally precise. Hard to read and reason about. |

**Lean:** Semantic versioning. Pin via `stacks.version` in `cartographer.toml` (not yet in the config schema -- add when this is resolved).

**Status:** Open. Blocks standards pack CLI behavior and the Standards Registry design.

---

### OQ-07: Binary document extraction when running outside a Claude Code session

**Question:** When `cartographer seed` is run from a plain terminal (outside a Claude Code session), Claude is not available via MCP for binary document extraction. What is the fallback behavior?

**Options:**

| Option | Tradeoff |
|---|---|
| Skip binary files with a warning | Simple. Binary docs never get seeded from CI or scripts. |
| Require a lightweight extraction library (`pypdf`, `python-docx`, `python-pptx`) as an optional dependency | Works everywhere. Adds dependencies. Extraction quality lower than Claude's. |
| Require Claude Code session for binary extraction; document the constraint | Honest. Users who need CI seeding use plain text formats. |

**Lean:** Skip with warning as the default. Add optional library extraction as a `pip install "cartographer-cli[extract]"` extra for teams that need it outside sessions.

**Status:** Open. Blocks the `seed` command implementation for binary formats.

---

## Phase 2 blockers

These questions do not block Phase 1 but must be resolved before Phase 2 implementation starts.

---

### OQ-08: Standards Registry storage backend

**Question:** What is the storage backend for the Standards Registry -- S3, an S3-compatible store (R2, MinIO), or a lightweight database-backed service?

**Why it matters:** The registry is append-only immutable versioned objects. S3 is a natural fit. R2 avoids AWS egress fees. MinIO works for fully self-hosted deployments.

**Lean:** S3 as the AWS reference deployment. S3-compatible interface documented so R2 or MinIO can substitute with a config change.

**Status:** Open. Blocks Standards Registry design.

---

### OQ-09: Standards web app auth and review model

**Question:** Who can author a standards pack draft, and who can approve it for publishing? Is approval one person or a quorum?

**Options:**

| Option | Tradeoff |
|---|---|
| Any authenticated user can author; any Reviewer can approve | Open. Low friction. Risk of low-quality content. |
| Authors must be designated per-pack; Reviewers are global | Pack-specific accountability. More admin overhead. |
| One approval required | Simple. Single point of approval. |
| Two approvals required (four-eyes principle) | Stronger quality control. Slower for small teams. |

**Status:** Open. Blocks web app auth design and the review screen spec.

---

### OQ-10: CLI fallback behavior when Standards Registry is configured but unreachable

**Question:** When `stacks.registry_url` is set and the registry is unreachable at `stack add` or `init` time, should the CLI fail loudly or fall back silently to bundled pack versions?

**Options:**

| Option | Tradeoff |
|---|---|
| Silent fallback, log a warning | Never breaks `init`. May silently use stale bundled versions. |
| Fail loudly if registry is configured | Forces the team to notice the outage. Breaks `init` on network issues. |
| Configurable: `stacks.registry_fallback = "warn" or "error"` | Flexible. Adds a config knob. |

**Lean:** Warn and fall back by default (`"warn"`), with `"error"` available for teams that want strict registry enforcement.

**Status:** Open. Blocks `stack add` and `init` implementation for the registry-fetch path.

---

## Closed questions

No questions have been closed yet. When a question is resolved, move it here with:
- The decision made.
- Who made it and when.
- A link to the ADR if one was written.

---

*To propose a resolution to any open question, open a discussion or PR against this file. Record the decision as an ADR in `docs/adr/` and link it here.*
