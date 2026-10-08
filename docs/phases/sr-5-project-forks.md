# Standards Registry Pass SR.5: Per-Project Forks

## Goal

Let a single project maintain its own diverged copy of a pack (standards/skills/agents) in the
registry, without affecting the shared global baseline or any other project -- copy the baseline
into a project-owned namespace once, then let that project's own developers push local edits back
to it going forward, using the project's existing shared bearer token.

**Added 2026-10-06, by explicit request.** This track's original scope (`standards-registry.md`)
listed "Registry-to-registry federation or multi-tenant registry" as explicitly out of scope for
SR.1-4. This phase knowingly reopens that line -- a deliberate decision, not scope creep discovered
during implementation.

**Entry condition:** SR.4 complete (the registry, auth, authoring, and admin layers all already
work; this phase only adds a per-project overlay on top of the existing S3 layout).

**Status: complete (2026-10-06).**

## Design decisions (confirmed before implementation)

1. **The fork lives in the registry (S3), not just locally.** A local-only "don't clobber edited
   files" approach was considered and rejected -- the divergence needs to survive across machines
   and CI, not just one developer's working copy.
2. **Changes flow in via a CLI push, with no SME review gate.** A project's own developers edit
   locally and push straight to their fork with the project's existing bearer token
   (`registry_tokens.project_id` -- already project-scoped, not user-scoped, since SR.2; no change
   needed there). The web app's SR.3 author/review/publish loop is untouched and stays scoped to the
   global baseline only.
3. **Forking must stay opt-in per project+pack, never automatic.** If every project silently forked
   on first use, no project would ever receive automatic baseline updates again -- the opposite of
   this track's whole point ("a project's next `stack add` picks it up, no CLI release"). A project's
   fetches hit the live global baseline exactly as before SR.5, until that project explicitly forks
   that specific pack.

## What shipped

**Registry (`webapp/backend/app/s3_registry.py`):** every pack-read/write function
(`get_latest`/`get_content_zip`/`put_content_zip`/`put_latest`) takes an optional `project_id`,
switching the S3 key prefix from `packs/...` to `projects/<project_id>/packs/...`. Two new functions:
`project_has_fork` (derived purely from S3 -- no new Postgres table) and `fork_pack_for_project`
(copies the pack's current baseline content types into the project's namespace under a fixed marker
version, `FORK_VERSION = "fork"` -- forks don't carry a version history; a push overwrites the one
live state rather than creating a new version).

**New API routes (`main.py`, bearer-token auth, same pattern as the existing CLI content route):**
- `POST /api/packs/{name}/fork` -- 409 if already forked (forking again would silently discard
  whatever was pushed since); copies baseline content if any exists, or creates an empty fork if
  the pack was never published globally but is registered (see the "closing gap 2" follow-up
  below) -- 404 only if there's neither a baseline nor a registered pack name.
- `PUT /api/packs/{name}/fork/{content_type}` -- 404 if no fork exists yet ("run `stack fork` first");
  otherwise a thin authenticated passthrough writing the raw request body to S3.
- `GET /api/packs/{name}/content/{content_type}` (existing route, modified) -- now tries
  `get_latest(name, project_id=project_id)` first; only falls back to the global lookup if that
  project has no fork of this specific pack. This one change is what makes forking transparent: once
  forked, the very next `stack add` for that pack picks up the fork with **zero CLI-side config
  change**, since the CLI already sends its project token on every fetch.

**CLI (`cli/src/cartographer/`):**
- `standards_registry.py` gained `fork_pack`/`push_fork_content` (the HTTP calls) and
  `build_flat_zip`/`build_skills_zip` (client-side zip building from an explicit file list, mirroring
  `scripts/publish_pack.py`'s archive-building conventions).
- `commands/stack.py` gained two new commands: `cartographer stack fork <pack>` and
  `cartographer stack push <pack>`.
- **The provenance problem:** `.claude/standards/<pack>/` is already pack-isolated, so building a
  push zip for standards is trivial. But `.claude/skills/` and `.claude/agents/` are shared,
  multi-pack-merged directories (`apply_pack` installs both `"core"` and the stack's own pack into
  the same tree) -- once installed, nothing on disk records which file came from which pack. Fixed by
  having `apply_pack` maintain a small manifest, `.cartographer/pack_provenance.json`
  (`{content_type: {pack_name: [filenames]}}`), updated on every run; `stack push` reads this to know
  exactly which currently-installed files belong to the pack being pushed, and zips their *current*
  on-disk content (so local edits are what actually gets pushed).

**Explicitly not built (keeps this simple, consistent with the no-review-gate decision):**
- No fork version history/changelog -- a fork has exactly one live state.
- No "rebase onto newer baseline" operation -- `stack fork` is refused once a fork exists,
  specifically so it can't accidentally wipe pushed changes; picking up new upstream baseline changes
  into an existing fork is a manual, project-side task (pull baseline, merge locally, push again).
- No web app UI visibility for forks -- the Standards/Skills/Agents sidebar views still show only the
  global baseline; forks are reachable only through the CLI's bearer-token path.
- No new Postgres table -- fork existence is derived purely from S3, same as the global baseline.

## Follow-up: `init --registry-url`/`--registry-token` (2026-10-06)

A brand-new `init` previously could never use the registry at all -- `apply_pack` ran before
`cartographer.toml`/`cartographer.local.toml` existed on disk, so `_resolve_registry_settings`
(`commands/stack.py`) always saw an unconfigured project on a first run, regardless of intent.
Picking up a project's own fork (or even just the shared baseline from the registry) required a
manual two-step dance: run `init` once bundled-only, hand-edit both config files, run again.

Fixed by adding `--registry-url`/`--registry-token` flags directly to `cartographer init` and
moving the config/local-override writes earlier in `init.py`'s `run()`, before its `apply_pack`
calls, so a token/url passed as flags are visible to `_resolve_registry_settings` on that same
first run. **Deliberately not a `--project-id` flag** -- which pack content gets served (shared
baseline, or this project's own fork if one exists) is still determined entirely by which bearer
token is provided, exactly as the rest of this design already works; a separate plaintext
project-id parameter was considered and rejected, since it would let anyone read any project's
fork just by naming it, with no token required at all.

Verified live: a brand-new project directory with `--registry-url`/`--registry-token` fetched
baseline content on its first-ever `init` call (previously impossible in one step). Forked and
pushed a distinctive edit from that project. A second, completely fresh project directory,
initialized from scratch with the *same* token, immediately received the fork
(`fetched vfork from registry`) on its own first-ever `init` call -- confirming token possession
alone determines fork access, with no separate identifier involved.

## Follow-up: forking a pack with no global baseline at all (2026-10-06)

The original design above only let a project fork and diverge from a pack that was *already*
published globally. A real use case doesn't fit that: an enterprise client (e.g. "Acme") with
standards/skills/agents that are entirely Acme-exclusive -- never meant to be a public baseline
pack at all -- but that should still be shared transparently across *all* of Acme's own projects,
the same way a fork of an existing pack already is. `stack fork` 404'd in this case, and even if it
hadn't, `apply_pack` (used by both `stack add` and `init`) separately hard-rejected any pack name
without a bundled `standards_packs/<name>/` directory -- so no project, including Acme's own other
ones, could ever pull a registry-only pack at all.

**The key insight enabling this for free:** `project_id` was never semantically tied to "one repo"
-- it's just whatever string an Admin picks when issuing a token, and `registry_tokens` has no
uniqueness constraint on it. An Admin can issue a separate token per Acme project while giving them
all the *same* `project_id` (e.g. `"acme-corp"`). Every one of those tokens resolves to the same
fork namespace, so once one Acme project forks+pushes a pack, every other Acme project -- each with
its own, different token -- transparently receives it. Nothing server-side needed to change for
this part; it was already true.

What actually needed fixing:
- `fork_pack_for_project` (`s3_registry.py`) no longer raises when there's no global baseline -- it
  creates an empty fork instead (`forked_from: None`). Guarded by a new `packs_admin.pack_exists`
  check in the fork route, so an unregistered, never-published name still 404s (no orphan S3
  prefixes from typos) -- an Admin must register the pack name first via `/api/admin/packs`.
- `apply_pack` (`commands/stack.py`) no longer requires a bundled `standards_packs/<name>/`
  directory when a registry is configured -- only when *neither* a bundled dir *nor* a registry
  exists does it still reject the name outright (preserves today's typo protection exactly for any
  project that hasn't adopted a registry at all).
- A pack resolving to *zero* content of any of the three types now prints a visible warning instead
  of silently reporting "0/0/0" -- catches the "wrong tenant" or genuine-typo case without
  reintroducing a hard failure for a legitimate, still-empty pack.
- `stack push`'s standards handling now reads `.claude/standards/<pack>/` directly from disk
  instead of the provenance manifest -- the directory was already pack-isolated, so the manifest
  indirection was never necessary, and this is what lets push work for a pack that was `fork`ed but
  never `stack add`-ed at all.
- New `cartographer stack adopt <pack> <skills|agents> <name>...` command: skills/agents live in
  shared, multi-pack directories with no inherent isolation, so (unlike standards) there's no way
  for `push` to know which installed file belongs to a hand-authored, never-bundled pack without
  being told. `adopt` validates the named file actually exists locally, then registers it into
  `pack_provenance.json` so `push` picks it up. Doesn't author the file itself.

**Still out of scope, by explicit decision:** no read-vs-push permission split within a shared
enterprise token -- any token resolving to `"acme-corp"` can both pull and push Acme's fork, same
as any other fork.

Verified live end to end: registered a throwaway pack (`packs_admin.create_pack`), issued two
tokens for the same `project_id` plus a third for a different one. Workspace A (token 1) forked the
unpublished pack (`forked_from: None`), hand-authored a standards file, a skill, and an agent file
with no `stack add` ever run, `adopt`ed the skill and agent, and pushed all three content types.
Workspace B -- a completely separate directory, using token 2 (same `project_id`, different raw
token, never forked anything itself) -- ran a plain `stack add` and received all three content
types transparently. Workspace C, using the third token (different `project_id`), got a visible
"has no content of any kind" warning and zero files -- confirmed no leak across tenants. Also
confirmed live: forking an unregistered name 404s, and forking an already-forked pack 409s. All
test S3 objects, Postgres rows, and local registry entries deleted afterward.

## Tests

16 new backend tests (11 `s3_registry`/route-level, mocked S3/tokens, following this repo's existing
`unittest.mock` conventions) plus a dedicated regression test proving an unforked project's fetch is
provably unaffected by another project's fork/push. 7 new CLI tests against the same local-`HTTPServer`
fixture pattern `test_stack_registry_fetch.py` established, covering `fork` (success/409/404), `push`
(success with a real zip-content assertion, "no fork yet" 404, "nothing installed" no-op), and the
provenance manifest's correctness after a real `stack add`. 3 more CLI tests (added with the
`init --registry-url`/`--registry-token` follow-up) cover: a brand-new project fetching on its very
first `init` call; `--registry-token` given without `--registry-url` warning and skipping fetch
rather than silently doing nothing; and a second `init` run updating an already-saved token.
3 more backend tests (added with the "closing gap 2" follow-up) cover the empty-fork creation path
and `packs_admin.pack_exists`. 9 more CLI tests (`test_stack_unpublished_pack.py`, with its own fake
server modeling registration/fork/content state) cover: forking an unregistered name (404) vs. a
registered-but-unpublished one (empty fork); `apply_pack` accepting an unbundled registry-only name
when a registry is configured, and still rejecting one when it isn't (regression); `push` working
with no prior `stack add`; `adopt`'s validation and happy path; and -- the single most important
case -- a second, completely separate workspace pulling the first workspace's pushed content via a
plain `stack add`.

## Verified live (real AWS S3 + Postgres, real `cartographer` CLI, not mocked)

- Issued a real project token (`tokens.issue_token`); fetched `python` standards unforked -- served
  the live global baseline (`v1.0.2`).
- `POST .../fork` -- real S3 objects landed at `projects/<id>/packs/python/fork/*.zip`; a second fork
  attempt correctly 409'd.
- Fetched again with the same token -- `X-Pack-Version: fork`, confirming the fork-first resolution.
- Pushed a modified `testing.md` via `PUT .../fork/standards` -- re-fetching returned the pushed
  content, confirming the push → fetch round trip.
- **Regression, the single most important check:** issued a second token for a project that never
  forked anything, fetched the same pack -- `X-Pack-Version: 1.0.2` (unchanged global baseline), no
  trace of the other project's fork content. Forking one project never leaks into or affects another.
- Real CLI end-to-end: `cartographer init --stacks typescript` (bundled, since the registry isn't
  configured on the very first `init` pass), configured `registry_url`/`registry_token`, re-ran
  `stack add typescript` (fetched baseline `v1.0.0`), ran `stack fork typescript` (confirmed the
  provenance manifest correctly separated `cross-stack`/`typescript` entries across all three content
  types), edited `.claude/standards/typescript/nestjs.md` locally, ran `stack push typescript`, deleted
  the local file, ran `stack add typescript` again with **no config change** -- output read
  `fetched vfork from registry`, and the pushed edit was back on disk.
- All test S3 objects, Postgres token rows, and local CLI registry entries created during
  verification were deleted afterward; the real bucket/database were left exactly as found otherwise.
