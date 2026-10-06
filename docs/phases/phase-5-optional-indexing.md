# Phase 5: Optional Indexing (KG/VDB Opt-Out)

**Status: complete (2026-10-06).**

## Goal

Let a user take advantage of Cartographer's standards/skills/agents packs without the KG/VDB
indexing machinery, for projects or teams that don't want a local knowledge index at all.

**Entry condition:** none — this is an independent, backward-compatible addition to the existing
`topology` config field (Phase 1's `local`/Phase 2's `central`), not a continuation of Phase 4's
scope. Added 2026-10-06, by request, after confirming via research that standards and skill packs
have zero dependency on indexing but agents do (see "Design decisions" below).

## Why this was needed

Research before this phase found:

- **Standards packs and all 15 bundled skill packs (core + stack-specific) have zero reference to
  the KG/VDB MCP tools anywhere** — pure markdown content, already safe to use without indexing.
- **`cartographer init` had no way to skip indexing.** Local VDB/KG provisioning was unconditional
  with no try/except — a provisioning failure aborted `init` entirely, before config was even
  written. `.mcp.json` registration, the four Claude Code hooks that keep the index current, and
  the `CLAUDE.md` block mandating "VDB and KG are your primary search tools... never run grep/find"
  were all written unconditionally too, regardless of whether indexing worked or was wanted.
- **`cartographer doctor` hard-failed (exit 1)** if the local VDB/KG weren't readable, with no way
  to tell it indexing was deliberately skipped.
- **All 43 bundled agent files** (18 core + 25 stack-specific reviewers/build-resolvers — corrected
  from an initial count of 42, see "Agent fallback content" below) declare and call
  `vdb_search`/`kg_query`/`kg_neighbors` as a mandatory first workflow step, with no "tool
  unavailable, fall back to Read/Grep" logic anywhere in the pack.

## Design decision

Agents still install normally when indexing is off, rather than being withheld. Most of an agent's
value is in its prompt/checklist content, not only its KG/VDB step; withholding all 43 agent files
would be a bigger behavior change for a `topology=none` user than keeping them available. Initially,
a real per-agent fallback rewrite was deferred as separate future work (content-authoring across
every file, not an architecture change) — it was then done in this same phase, see "Agent fallback
content" below.

## What shipped

Extended the existing `Topology` literal (`cli/src/cartographer/config.py`) with a third value:

```python
Topology = Literal["local", "central", "none"]
```

Default stays `"local"` for new projects, unchanged — opting out is always an explicit
`--topology none`, never implicit.

**`cartographer init`** (`commands/init.py`): everything that exists solely to serve indexing is now
gated behind `indexing_enabled = topology != "none"`:
- Local VDB/KG provisioning — skipped entirely when disabled.
- `.mcp.json` registration — `ensure_mcp_json(workspace, {} if not indexing_enabled else ...)`. No
  change needed in `claude_merge.py`'s `_ensure_json`: it already no-ops cleanly on an empty
  `additions` dict, so passing `{}` was sufficient.
- The four Claude Code hooks — same `{}`-when-disabled pattern via `ensure_settings_json`.
- `archaeology`/`recall` skill installation — skipped; both exist specifically to bootstrap/query an
  index that won't exist.
- `CLAUDE.md` — a new, shorter block (`CARTOGRAPHER_CLAUDE_MD_BLOCK_NO_INDEX` in `claude_merge.py`)
  replaces the VDB/KG-mandatory one: keeps the "standards live under `.claude/standards/`" pointer,
  drops the mandate and the "never grep" hard rules, and explicitly tells Claude to fall back to
  `Read`/`Grep`/`Glob` for anything a tool-less skill/agent would otherwise have looked up.
  `ensure_claude_md` now takes a `block` parameter so callers choose.
- `apply_pack` (standards/skills/agents installation) is completely untouched — runs identically
  regardless of topology, confirming the "standards/skills are already safe" research finding.
- Switching an *existing* project to `--topology none` never deletes `.cartographer/local/` if one
  already exists — it only stops provisioning/maintaining it going forward, consistent with this
  codebase's existing non-destructive-by-default pattern (same posture as `init`'s pre-existing
  config-preservation behavior on re-runs).

**`cartographer doctor`** (`commands/doctor.py`): local VDB/KG readability, the `cartographer serve`
running-check, `.mcp.json` wiring check, and the KG edge-taxonomy-drift query are all now gated
behind the same `indexing_enabled` check, printing one INFO line instead ("indexing disabled
(topology=none) -- skipping local KG/VDB checks") rather than FAILing. Central-topology checks are
unaffected — `"central"` still implies local indexing is also active, unchanged from before this
phase. The taxonomy-version-drift check (comparing `cfg.taxonomy.version` to the installed CLI's
canonical version) is independent of indexing and was left unconditional.

`cartographer.example.toml`'s `[topology]` comment documents the new `"none"` option.

## Agent fallback content

All 43 bundled agent files (`cli/src/cartographer/agents_packs/{core,<stack>}/*.md`) now carry an
explicit fallback note at the point where they'd otherwise call `vdb_search`/`kg_query`/
`kg_neighbors`, added one file at a time (read → edit → review each, no batch find/replace, no
subagent delegation — by explicit request, since a mechanical batch edit across 43 differently-
structured files risks subtle mismatches). Three structural patterns, each with a tailored fallback:

- **16 stack reviewers** share a literal `## Cartographer knowledge index` section with an identical
  closing sentence ("Run these after identifying changed files from the diff..."). Fallback:
  `Grep` for the changed file's symbol/class/module names to approximate callers and importers.
- **9 stack build-resolvers** (plus core's `build-error-resolver`) embed one `vdb_search`/`kg_query`
  call inline in their diagnostic workflow. Fallback: `grep -rn` for imports of the error file and
  the missing symbol's definition — most of these already had a parallel grep-based section (e.g.
  Go's "Module Troubleshooting", Django's "Import Errors") the note points back to.
- **18 core agents** vary most: six (`code-explorer`, `refactor-cleaner`, `code-simplifier`,
  `architect`, `planner`, `comment-analyzer`) treat the KG/VDB as the *mandatory first step* of their
  whole process and got a substantial, multi-line fallback describing an equivalent Glob/Grep-based
  procedure; the rest got a shorter note, several explicitly pointing to a pattern-scan section the
  file already had as a KG complement (e.g. `silent-failure-hunter`'s Step 2, `refactor-cleaner`'s
  static-analysis step) and reframing it as the primary method rather than a supplement when the KG
  is absent entirely.

**No change to what `archaeology`/`recall` themselves do** — they're just not installed when
topology is `"none"` (see "What shipped" above), same content otherwise.

## Tests

4 new tests in `cli/tests/test_init.py`: `topology=none` installs packs but skips every indexing
artifact (`.cartographer/local/`, `.mcp.json`, `.claude/settings.json`, `archaeology`/`recall`);
`CLAUDE.md` omits the VDB/KG mandate but keeps the standards pointer; switching to `none` on an
existing project never deletes an already-provisioned local index; `doctor` exits 0 (not 1) on a
`topology=none` project with no local index at all.

Agent fallback content has no dedicated automated tests (it's prose, not executable logic) --
verified instead by a scripted check that every one of the 43 files contains the fallback phrase,
plus a YAML-frontmatter-integrity check across all 43 (confirms no edit corrupted a file's `tools:`
declaration or closing `---` delimiter) and a full CLI test suite run to confirm no test depends on
exact agent file wording.

## Published to the registry as the new baseline (2026-10-06)

The 43-file agent fallback content was published to the real Standards Registry S3 bucket via
`scripts/publish_pack.py`, becoming the new baseline every project's next `stack add`/`init --stack`
picks up: `core`, `dart`, `golang`, `java`, `kotlin`, `react`, `rust`, `swift`, `typescript`, `vue` →
`1.0.1`; `python` → `1.0.3` (it was already at `1.0.2` from an earlier SR.3 web-app-authored change).
`cross-stack` and `angular` were not republished -- neither has any agent content to begin with
(`angular` has no stack-specific agents at all; `cross-stack` is standards-only), so nothing in them
changed.

Each publish included standards+skills+agents together (or skills+agents for `core`, which has no
standards), not agents alone -- a pack version is one complete bundle; publishing agents only at a
new version number would have orphaned that version's standards/skills at the old version path.

**Incidental fix, discovered during verification, not something this session caused:** the live
`python` pack's `1.0.2` `patterns.md` turned out to contain leftover content from SR.3's "test
reject-revise flow" verification pass (literally the string `# test reject-revise flow`) -- a test
draft that got approved and published to the real bucket during that earlier verification and was
never cleaned up afterward. Republishing from the bundled source at `1.0.3` replaced it with the
real patterns content; confirmed via a diff of the two versions' `standards.zip` that this was the
only file affected. By explicit direction, the bundled `cli/src/cartographer/standards_packs/`
source is treated as canonical here, so no further reconciliation was needed.

**Noted, not acted on (pre-existing, out of scope for this session):** `agents_packs/` has four
directories -- `cpp`, `csharp`, `fsharp`, `php` -- with no corresponding `standards_packs/`/
`skills_packs/` directories and no entry in `stack.py`'s `KNOWN_PACKS`. They were not published
(the registry has no pack by these names) and aren't reachable via `stack add` today regardless --
`_bundled_pack_dir` rejects an unknown pack name before agent content would even matter. Fixing this
(whether by adding full standards/skills packs for these languages or removing the orphaned agent
directories) is a separate decision, not part of this change.

## Verified live

`cartographer init --path /tmp/no-index-demo --stacks python --topology none`: confirmed by hand
that no `.cartographer/local/`, `.mcp.json`, or `.claude/settings.json` were created, while
`.claude/standards/python/`, 20 core skills, and 22 agent files installed normally. `cartographer
doctor` on that project exited 0 with an INFO line, not a FAIL. Diffed `CLAUDE.md` against a normal
`--topology local` init in a second scratch project — the `none` version correctly omits "VDB and
KG are your primary search tools" while keeping "Standards live under `.claude/standards/`" — and
confirmed the `local` project's `doctor` output (`OK local VDB opens` / `OK local KG opens` / `OK
Cartographer MCP entries present`) is completely unaffected by this change, a straight regression
check. Both scratch projects and their registry entries were deleted afterward.
