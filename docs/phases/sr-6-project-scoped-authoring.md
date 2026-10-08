# Standards Registry Pass SR.6: Project-Scoped Authoring in the Web App

## Goal

Let a Cognito-authenticated human (Author/Reviewer/Admin) create and edit a **project-scoped pack**
(a registry-only pack with no global baseline, living in a project's own fork namespace --
see [SR.5](sr-5-project-forks.md)'s "closing gap 2" follow-up) through the web app's existing
editor/draft UI, instead of that pack only being reachable by hand-authoring files locally and
running `cartographer stack adopt`/`stack push` from the CLI.

**Added 2026-10-08, by explicit request**, after building exactly this kind of pack by hand
(`cox-aws-sandbox`, see [project_standards_webapp memory]) and hitting the gap directly: an Author
logged into the web app cannot see, let alone edit, a pack that only exists as a project fork,
because the browser UI's pack-listing and draft/review/publish routes have **no `project_id`
concept anywhere** -- `SessionUser` (Cognito identity) and `project_id` (registry-token identity)
are two completely separate systems today, by original SR.2 design, and SR.5 deliberately kept it
that way ("the web app's SR.3 author/review/publish loop is untouched and stays scoped to the
global baseline only").

This phase knowingly reopens that line. It is not a bug fix -- the current separation was
intentional -- it's a scope expansion, same as SR.5 was for the "no multi-tenant registry" line.

**Entry condition:** SR.5 complete (done). No new infrastructure needed -- this is additive to the
existing Postgres (`drafts`/`draft_comments`/`packs`) and S3 (`projects/<id>/packs/...`) layout.

**Status: design confirmed 2026-10-08, implementation not started.** All five open questions below
are now decided. This document records the decisions before any code changes, same discipline SR.5
used.

## Why this is harder than it sounds: the core tension

Every existing SR.2-SR.5 permission boundary is built around **one** identity concept at a time:
Cognito groups (Author/Reviewer/Admin) gate the browser UI; a bearer token's `project_id` gates the
CLI. This phase needs **both at once** -- a specific human, with a specific Cognito role, acting on
behalf of a specific project -- and that combined relationship doesn't exist in the data model
anywhere yet. Every decision below is a consequence of that one gap.

## Design decisions (confirmed 2026-10-08, before implementation)

1. **New Postgres table maps Cognito users to projects.** `project_members(project_id TEXT NOT
   NULL, email TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY
   (project_id, email))`. Many-to-many: one user can belong to multiple projects, one project can
   have multiple members. Role (Author/Reviewer/Admin) stays exactly where it already lives --
   Cognito groups -- this table only answers "which project(s) is this email associated with,"
   never "what can they do once there." A project-scoped pack is only visible/editable to users
   with a row in this table for that `project_id` -- closing the gap flagged in the original Q1
   option 3 (no, visibility does *not* stay open to every Cognito user; it matches the same
   invisibility `cox-aws-sandbox` already has for the CLI/bearer-token path).

2. **The review gate applies to web-authored project packs; the CLI path is unchanged.**
   Project-scoped content now has two legitimate write paths with two different governance models,
   by design, not by oversight:
   - CLI (`stack adopt`/`stack push`): unchanged, no review, gated purely by bearer token possession
     (exactly as SR.5 built it).
   - Web UI: full Draft -> In Review -> Approved -> Published state machine, identical to how the
     global baseline already works -- no special-cased "skip review because it's project-scoped"
     logic. If you author through the browser, it gets reviewed, period.

3. **A published project-scoped draft writes to the same fork location a CLI push would use** --
   `projects/<project_id>/packs/<name>/fork/...`, no separate versioned lineage for web-authored
   content. **Collision between CLI and web writers is an accepted risk, not mitigated in this
   phase.** If a CLI push and a web publish happen close together, one wins and the other is
   silently overwritten, same as two CLI pushes racing would already behave today -- no new locking,
   no merge step, no warning banner. Document this plainly in the feature's own UI copy so it isn't
   a silent surprise to the first team that hits it.

4. **Authors can create project-scoped packs directly, no Admin step first.** This does *not*
   loosen the existing Admin-only gate on creating a **global** pack name (`packs_admin.create_pack`
   stays Admin-gated exactly as today for anything intended to become shared baseline content). It
   adds a new, separate, lower-privileged path: an Author who is a member of a project (per
   decision 1's table) can create a brand-new pack name *and* fork it into their own project's
   namespace in one action -- a single new endpoint, not a relaxation of the existing admin route's
   permission check. That new pack name still lands in the shared `packs` table (needed for the
   existing `fork_pack_for_project`/`pack_exists` 404 guard to keep working unchanged), it's just
   that *who* can trigger that insert gains a second path alongside Admin's existing one.

5. **`drafts` gets a new nullable `project_id` column, with an explicit backfill.** `ALTER TABLE
   drafts ADD COLUMN project_id TEXT; UPDATE drafts SET project_id = NULL WHERE project_id IS
   NULL;` -- the backfill is a no-op in value (existing rows have no project, correctly represented
   as `NULL` = "this is a global-baseline draft") but is still run explicitly, as its own migration
   step, matching this repo's own `database-migrations` conventions rather than leaving an implicit
   "newly added columns default to NULL" assumption undocumented. `publish.py` branches on whether
   `project_id IS NULL` to decide which S3 prefix (global baseline vs. this project's fork) to write
   to -- see decision 3.

## Explicitly out of scope for this phase (revisit later if needed)

- Per-project review workflows, SLAs, or notification settings -- whatever the review-gate answer
  above turns out to be, it applies uniformly, not configurably per project.
- A UI for Admins to manage `project_members` rows beyond the minimum needed to prove the feature
  end to end (bulk import, self-service join requests, etc.).
- Migrating `cox-aws-sandbox`'s existing CLI-pushed content into this new data model -- that pack
  stays CLI-managed; this phase proves the feature on a **new** pack, not a retrofit of an existing
  one.
- Any change to how the CLI's `stack fork`/`stack push`/`stack adopt` commands work -- this phase is
  additive (a second way to reach the same fork namespace), not a replacement. Decision 2 means the
  CLI path explicitly keeps its current no-review behavior forever, not just for this phase.
- Resolving the CLI/web write collision from decision 3 -- accepted risk, not solved here.
- A permission split between Author and Reviewer *within* a project (e.g. only some project members
  can approve) -- project membership alone determines access; role within the project still comes
  from the user's existing Cognito group (Author/Reviewer/Admin), unchanged.

## What this phase builds

- **Schema**: `project_members` table (decision 1); `drafts.project_id` nullable column + backfill
  (decision 5).
- **New endpoint**: Author-permitted "create a project-scoped pack" (decision 4) -- inserts into
  `packs` (same table Admin's route uses) and calls `fork_pack_for_project` in one step, gated on
  the caller having a `project_members` row for the target `project_id`, not on Admin group
  membership.
- **`drafts.py`/`main.py`**: every draft route becomes project-aware -- creating a draft for a
  project-scoped pack stamps `project_id` from the caller's project membership; the existing review
  routes (submit/approve/reject) are otherwise unchanged, since decision 2 means the state machine
  itself doesn't branch, only the final publish destination does.
- **`publish.py`**: branches on `draft.project_id IS NULL` -- `NULL` writes to the global baseline
  exactly as today; a real value writes to `projects/<project_id>/packs/<name>/fork/...`, the same
  location `stack push` targets (decision 3).
- **Frontend**: a new, separate "My Project Packs" sidebar surface (not merged into the global
  Standards/Skills/Agents views, so project-exclusive content never appears alongside public
  baseline content) -- listing only packs the current user has a `project_members` row for, with a
  "new pack" action that calls the new Author-permitted create endpoint.

## Exit criteria

- [ ] An Author who is a `project_members` row for project X can see project X's pack(s) in the new
      UI surface, and cannot see project Y's packs there.
- [ ] That Author can create a new project-scoped pack directly (no Admin step), and create/edit/
      submit a draft for it; the draft goes through the full Draft -> In Review -> Approved ->
      Published state machine before publish, same as a global-baseline draft.
- [ ] A user with no `project_members` row for project X cannot see or create drafts for project X's
      packs through the UI.
- [ ] A real end-to-end pass, mirroring every prior SR phase's verification discipline: create a
      project-scoped pack through the UI, author -> submit -> review -> approve -> publish a draft
      for it, and confirm a real `cartographer stack add` with that project's bearer token picks it
      up -- and a different project's token still does not.
- [ ] A real collision check, since decision 3 explicitly accepts this risk rather than solving it:
      `cartographer stack push` the same pack from the CLI after a web publish, confirm the CLI push
      wins (last-write-wins, no error, no merge) -- documents the accepted behavior rather than
      leaving it theoretical.
