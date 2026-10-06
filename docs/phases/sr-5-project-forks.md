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
  whatever was pushed since), 404 if the pack has no baseline to copy from.
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

## Tests

16 new backend tests (11 `s3_registry`/route-level, mocked S3/tokens, following this repo's existing
`unittest.mock` conventions) plus a dedicated regression test proving an unforked project's fetch is
provably unaffected by another project's fork/push. 7 new CLI tests against the same local-`HTTPServer`
fixture pattern `test_stack_registry_fetch.py` established, covering `fork` (success/409/404), `push`
(success with a real zip-content assertion, "no fork yet" 404, "nothing installed" no-op), and the
provenance manifest's correctness after a real `stack add`.

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
