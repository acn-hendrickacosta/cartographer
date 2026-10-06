# Standards Registry Pass SR.3: Web App -- Authoring, Review, and Publish

## Goal

An SME authors a new version of a standards pack in the web app, it passes review under the one-approval model (OQ-09), and a project's next `cartographer stack add` picks it up -- with no CLI release and no PR to the Cartographer repository. This is the track's original top-level goal, and the single most important exit criterion of this sub-phase, the same way Phase 1's recall loop was "the single most important exit criterion" for that phase.

**Entry condition:** SR.2 complete (auth, read views, and a reachable registry to publish into already exist).

**Status as of 2026-10-06: complete, verified against real infrastructure (Postgres, S3, Cognito), not mocked.**

- **Rescoped on implementation** to cover all three content types (standards/skills/agents) symmetrically, not standards-only as this doc originally described. This doc predated SR.2's later decision to treat all three types symmetrically (separate sidebar destinations, separate registry schema per type) -- carrying that forward, a draft is `(pack_name, content_type, file_name)`, not just `(pack_name, file_name)`. Routes became `/{standards,skills,agents}/:name/drafts/new` (optionally `?file=<existing-filename>` to prefill) and `/{...}/:name/drafts/:draftId/edit`, not the originally-documented `/packs/:packName/drafts/...`. Review queue (`/review`) lists drafts across all three types; review screen (`/review/:draftId`) is still per-draft, unchanged in spirit.
- **Backend** (`webapp/backend/app/drafts.py`, `publish.py`, routes in `main.py`): `drafts` and `draft_comments` tables in the same Postgres database as SR.2's registry tokens. State machine transitions are atomic single-statement `UPDATE ... WHERE id = %s AND state IN (...)` guards (`drafts.transition`), not read-then-write, so there's no race window. One-approval enforcement (OQ-09) and author-only-edit checks are server-side in `main.py`'s route handlers, not just hidden in the UI. Publish reassembly (`publish.py`) fetches the pack's current archive for that content type (if any), replaces/adds the drafted file, and re-zips -- `s3_registry.build_zip_from_files` treats a flat key (`testing.md`) or a nested key (`archaeology/SKILL.md`) identically, so standards/agents/skills share the same reassembly code path. 30 new unit/API tests (62 total in the backend now).
- **Frontend** (`webapp/frontend/src/views/PackEditor.jsx`, `ReviewQueue.jsx`, `ReviewScreen.jsx`): "Edit" links added to `PackDetail`'s file cards (Author role only) and a "+ New file" action; a "Review queue" sidebar item appears only for the Reviewer role. The review screen's "diff" is a side-by-side published-vs-draft view, not a line-level diff (no diff library in scope).
- **End-to-end proof, run live via Chrome DevTools MCP against the real server (not mocked):** logged in as the seeded Author, opened `python`'s `testing.md`, created a draft (prefilled from the real published content, version auto-incremented), submitted it; logged in as the seeded Reviewer (a different user), opened the review queue (confirmed sidebar-gated to Reviewer role), viewed the side-by-side diff, approved, confirmed publish. Verified directly against the real S3 bucket: `latest.json` and a new `version.json` were written correctly. Ran the real `cartographer stack add python` against the real server and confirmed the CLI picked up the new version with all 11 files intact (10 unchanged + 1 edited). Separately verified reject -> revise -> resubmit -> approve -> publish end to end via direct API calls with real session cookies for both roles, including confirming a 403 when the Author tried to approve their own draft.
- **A real bug caught during this pass, unrelated to the new code:** the webapp server's AWS credentials had expired mid-session (`ExpiredToken`, a stale cached token in the long-running server process, not a code defect) -- caught because a live S3-backed request actually failed with a 500, not because of any test. Fixed by restarting the server process so it re-resolved credentials fresh.
- **Not done:** no automated browser test suite (Playwright/Cypress) -- verification was manual (Chrome DevTools MCP) plus the 62 backend unit/API tests. No diff highlighting in the review screen (plain side-by-side, as noted above).

---

## Scope

### In scope

| Component | What ships |
|---|---|
| Draft/review state store | PostgreSQL -- **decided 2026-10-05** (was previously left open as "DynamoDB or RDS, implementation detail"), specifically the same instance SR.2's `registry_tokens` table already lives in, as its own tables in the `cartographer_webapp` database. Reuses `webapp/backend/app/db.py`'s connection pool -- no new stateful service to provision for this phase. |
| Pack editor | `/{standards,skills,agents}/:name/drafts/new` (optionally `?file=<existing-filename>`) and `/{...}/:name/drafts/:draftId/edit` -- markdown editor (plain textarea, not split-pane -- see note below), submit for review |
| Review queue | `/review` -- drafts in IN REVIEW state, across all three content types and packs |
| Review screen | `/review/:draftId` -- side-by-side published-vs-draft view (not a line-level diff), comment thread, approve/reject under the one-approval model |
| Publish flow | Publish confirmation modal (triggered after Approve) -- writes to S3, updates `latest.json`, transitions state to PUBLISHED |
| Pack version state machine | `DRAFT -> IN REVIEW -> APPROVED -> PUBLISHED`, with `REJECTED -> DRAFT` (revise and resubmit) |

### Explicitly out of scope (deferred to SR.4)

- Admin screens (user management, pack management, creating new pack names)
- Migrating the one-time bundled-pack publish mechanism away from SR.1's admin script -- that script can coexist indefinitely for break-glass use; nothing requires removing it

---

## Component breakdown

### 1. Draft/review state store

Holds DRAFT/IN REVIEW/APPROVED/REJECTED records -- never PUBLISHED, which lives only in S3 as the immutable source of truth. A draft record needs at minimum: pack name, target version, **file name within the pack** (a draft edits one file, not the whole pack -- see §5), Author, file content, state, comments, timestamps. Schema is an implementation detail for whichever store is chosen; no interface contract needs to be fixed in this doc beyond "drafts are not in S3."

### 2. Pack version lifecycle (OQ-09 applied)

```
DRAFT -> IN REVIEW -> APPROVED -> PUBLISHED
                  \-> REJECTED -> DRAFT (revised)
```

| State | Meaning | Who can act |
|---|---|---|
| DRAFT | Being edited by its Author. Not visible to CLI fetches. | Author: edit, submit for review, discard |
| IN REVIEW | Submitted. Locked for editing. | Reviewer (not the Author): approve or reject |
| APPROVED | Approved, not yet in the registry. | Reviewer who approved: confirm publish |
| PUBLISHED | Immutable version in the S3 registry. | No one -- terminal state. Corrections require a new draft with a new version number. |
| REJECTED | Returned to the Author with required comments. | Author: revise (returns to DRAFT) |

One-approval enforcement (OQ-09 decision): any Reviewer other than the draft's own Author may approve. The editor/approve action must check `draft.author != current_user` server-side, not just hide the button client-side.

### 3. Pack editor

```
/{standards,skills,agents}/:name/drafts/new?file=<existing-filename>   (or no ?file= for a brand-new file)
/{standards,skills,agents}/:name/drafts/:draftId/edit                  (resume an existing draft)
  Shows: file name field (editable only before the first save),
         plain markdown editor (textarea, not split-pane -- no live preview
           or diff-within-the-editor; the review screen is where
           published-vs-draft is shown side by side, not here),
         version number field (auto-incremented from the pack's current
           published version, editable, applies to the whole publish, not
           just this file),

  Actions:
    [Save]              -> Create the draft on first save (if new), or update it
    [Submit for review] -> Validate version is higher than current published.
                           Transition draft to IN_REVIEW. Lock editor. Redirect to pack detail.
    [Discard draft]     -> Confirm dialog. Deletes the draft (DRAFT state only). Redirect to pack detail.
```

### 4. Review queue + review screen

```
/review
  Shows: drafts in IN_REVIEW state across all packs and content types,
         ordered by submission date -- pack name, content type, file name,
         version, Author, submission date

/review/:draftId
  Shows: side-by-side published-vs-draft content, metadata, comment thread,
         approve / reject controls (approve/reject disabled server-side,
         not just hidden, if current_user == draft.author_email)

  Actions:
    [Add comment]  -> General comment on the draft, saved immediately
    [Approve]      -> Transition to APPROVED. A "Confirm publish" button
                      appears once APPROVED (no separate modal -- same screen).
    [Reject]       -> Require a comment (prompted for it). Transition to REJECTED.
```

### 5. Publish flow

- Triggered by the publish confirmation modal immediately after Approve (`APPLICATION_ARCHITECTURE.md` §2.5)
- Zips the pack's reassembled files (every file from the current published version of this content type, with the drafted file replacing/adding to it) and writes the archive to `s3://packs/<name>/<version>/<content_type>.zip`, plus `s3://packs/<name>/<version>/version.json` (metadata: `published_at`, `published_by`, `changelog`) -- same object shape SR.1's admin script produces, per `sr-1-registry-infrastructure.md`'s schema
- Writes/updates `s3://packs/<name>/latest.json`
- Transitions the draft/review record to PUBLISHED; this record is now historical only -- the S3 object is the source of truth going forward
- This is the first phase where the web app itself writes to S3 (SR.1 used the admin script; SR.2 was read-only)
- A draft edits **one file within a pack**, not the whole archive -- a pack like `cross-stack` has 28 `.md` files (per `components/standards-packs.md`), and a single split-pane editor across all of them at once doesn't make sense. The pack editor (§3) lets an Author pick an existing file from the pack's current published version (or add a new one) to create a draft against. On publish, the backend assembles the new version's zip server-side: every file from the pack's current latest version, with the drafted file(s) replacing their prior content (or added, if new). This is why "version number" is a property of the whole publish operation, not of an individual file's draft.

---

## Build order

```
1. Provision draft/review state store
2. Pack editor: draft create/edit/diff/save
3. Submit for review -> IN REVIEW transition
4. Review queue + review screen, with one-approval enforcement
5. Approve -> publish confirmation modal -> S3 write -> PUBLISHED transition
6. Reject -> REJECTED -> revise -> resubmit loop
7. End-to-end acceptance test (below)
```

---

## Exit criteria

| # | Criterion | How to verify | Verified |
|---|---|---|---|
| 1 | An SME can log in, create a draft of an existing pack, and submit it for review | Walk through the author flow end to end | **Yes** -- browser, real Cognito login as the seeded Author, real draft created and submitted (`python`/`testing.md`) |
| 2 | A different user with the Reviewer role can view the draft, comment, and approve it | Walk through the review flow; confirm the Author themself cannot approve their own draft (server-side check, not just hidden UI) | **Yes** -- browser, real login as the seeded Reviewer, approved; separately confirmed via direct API call that the Author's own approve attempt gets a real 403 |
| 3 | After approval, confirming publish writes the new version's zip + `version.json` to S3 with correct keys and updates `latest.json` | Inspect S3 directly after publish | **Yes** -- `aws s3api get-object` against the real bucket after publish showed the correct `version.json` and an updated `latest.json` |
| 4 | `cartographer stack add <pack>` on a project with `registry_url` and a valid `registry_token` configured fetches the newly published version through the authenticated content endpoint | Run it; inspect `.claude/standards/<pack>/`; confirm the edited file's new content is present and every other file in the pack is still there unchanged | **Yes** -- real CLI run against the real server; all 11 files present (10 unchanged, 1 updated) |
| 5 | A published version is immutable -- there is no UI path to edit it | Attempt to edit a published version; confirm no editor is reachable for it, only "new draft" | By construction, not separately browser-tested: `PackDetail`'s "Edit" links always route to `/drafts/new`, never to an existing published file in place; the backend has no endpoint that writes to an already-`PUBLISHED` S3 object directly |
| 6 | Reject -> revise -> resubmit -> approve -> publish works end to end | Walk through a full reject-then-fix cycle | **Yes** -- via direct API calls with real session cookies for both roles against the live server; ended with a real second publish (`python` v1.0.2) |

**The single most important exit criterion:** the full loop -- author, review, publish, CLI delivery -- demonstrated live end to end (criterion 4, in context of 1-3). Demonstrated for real, not mocked, the same bar Phase 1 held itself to for its own recall loop. See this doc's status note at the top for the full verification narrative.

---

## Test approach

**Unit tests (web app backend):**
- Pack version state machine: every valid and invalid transition, including the one-approval author/reviewer check.
- Publish operation: correct S3 key structure; `latest.json` update; state set to PUBLISHED.

**Integration tests (web app + S3):**
- Create draft -> submit -> approve -> publish; verify S3 objects (`<content_type>.zip`, `version.json`, `latest.json`) exist with correct content, and that the zip contains every file from the prior version plus the drafted change.
- Fetch `latest.json` after publish; verify version is correct.

**Browser tests (Playwright or Cypress):**
- Author flow: login -> create draft -> edit -> submit for review.
- Review flow: login as a different user with Reviewer role -> open review queue -> approve -> publish.
- Read-only verification: published version editor is unreachable.

**End-to-end acceptance test (the exit criterion, scripted):**

```
1. Author logs into the web app
2. Picks an existing file in a pack, creates a draft with a recognizable change
   (add a distinctive line to it)
3. Submits for review
4. A different user (Reviewer role) logs in, reviews, and approves
5. Confirms publish
6. Run: cartographer stack add <pack>   (registry_url + registry_token configured)
7. Open .claude/standards/<pack>/<the edited file>
8. Confirm the distinctive line from step 2 is present, and every other file in
   the pack is still there with its prior content unchanged
```

---

*Next: [sr-4-webapp-admin.md](sr-4-webapp-admin.md) adds user and pack management -- lower risk, and not on the critical path to the loop this phase just closed.*
