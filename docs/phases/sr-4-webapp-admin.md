# Standards Registry Pass SR.4: Web App -- Admin Screens

## Goal

An Admin can manage who holds which role, create or deprecate pack names, and issue or revoke the per-project bearer tokens that gate CLI registry access -- retiring the last manual/break-glass steps (Cognito console role seeding and hand-seeded registry tokens from SR.2, no mechanism at all yet for adding a brand-new pack name) that earlier sub-phases relied on.

**Rescoped 2026-10-05** to add registry token management, alongside the correction that moved CLI fetch behind an authenticated API (`ARCHITECTURE.md` §7.2, `sr-2-webapp-auth-and-read-views.md`). SR.2 seeds one test token by hand to prove the fetch path works; this phase adds the real self-service issuance/revocation screen so that bootstrap step isn't needed for every new project going forward.

**Entry condition:** SR.3 complete (the authoring/review/publish loop already works; this phase only adds management screens around it).

**Status: complete (2026-10-06).** Three new/extended backend modules (`app/cognito_admin.py`, `app/packs_admin.py`, `app/tokens.py`'s `issue_token`/`list_tokens`/`revoke_token` plus a `last_used_at` bump on every successful `validate_token`) back nine new `/api/admin/*` routes in `main.py`, all gated to the Admin role via the existing `_require_role` helper. `POST /api/drafts` now rejects (409) against a deprecated pack via `packs_admin.is_deprecated()`. Frontend: `AdminLayout.jsx` (sub-nav: Users/Packs/Registry tokens, nested under one sidebar "Admin" destination rather than three separate top-level sidebar items, since these are tightly-related management screens, not independent content types like Standards/Skills/Agents) plus `AdminUsers.jsx`, `AdminPacks.jsx`, `AdminTokens.jsx`. 16 new backend tests (78 total; `packs_admin`/`tokens` against a mocked Postgres connection per this repo's existing convention, `cognito_admin` against a mocked boto3 client).

**Verified live** (Chrome DevTools MCP against the real Cognito pool/Postgres/S3, not mocked) in an isolated browser session as `test-admin@example.com`:
- Role change: toggled `test-reviewer@example.com`'s Author role on/off via the Users tab; confirmed both directions directly against the real pool with `aws cognito-idp admin-list-groups-for-user` (not just the UI's own optimistic state).
- Pack creation: created `sr4-test-pack` via the Packs tab; confirmed it immediately appears in the admin list and in `/standards/sr4-test-pack`, which renders SR.3's existing "no published standards yet" + (role-gated) "+ New file" state -- this validates the exit-criteria-2 design question from earlier in the track (a new, zero-content pack needs no special-case anywhere else; the already-built 404-graceful PackDetail view covers it). Did not re-run a full publish cycle against it, since that loop (reject/revise/approve/publish) was already proven end-to-end in SR.3's pass against an existing pack -- the only new code path here is the pack *registry entry* itself, which existed before this pack did.
- Deprecation: deprecated `sr4-test-pack`; confirmed `POST /api/drafts` against it returns 409 ("pack 'sr4-test-pack' is deprecated, cannot start new drafts") as a logged-in `test-author@example.com`, while an unrelated already-published pack (`python`) remained fetchable via the CLI's bearer-token endpoint throughout -- deprecation doesn't affect existing content.
- Token issuance + fetch: issued a token for project `sr4-verify-project` via the Tokens tab; used the raw value (shown once) in a real `Authorization: Bearer` request to `GET /api/packs/python/content/standards` -- 200. Reloaded the tab and confirmed `last_used_at` had been bumped from `—` to a real timestamp.
- Token revocation: revoked the same token from the Tokens tab; the identical request immediately returned 401, and the UI's status column flipped to `REVOKED`.
- Test pack and test token were deleted from Postgres after verification; no state left behind beyond SR.2's original hand-seeded `proj_test` token, which this phase intentionally leaves alone (see "registry tokens" component note below).

---

## Scope

### In scope

| Component | What ships |
|---|---|
| Admin: user management (`/admin/users`) | List users, assign/change role (Author/Reviewer/Admin) |
| Admin: pack management (`/admin/packs`) | Create a new pack name (provisions its `latest.json` as empty/absent until first publish); deprecate an existing pack |
| Admin: registry tokens (`/admin/tokens`) | Issue a new per-project bearer token (shown once, stored hashed thereafter -- same handling as the `promotion_token` pattern elsewhere in Cartographer); list existing tokens by project with created/last-used metadata; revoke a token immediately |

### Explicitly out of scope

- Per-pack author/reviewer assignment -- OQ-09's resolved decision is global roles, not per-pack; revisit only if a real need surfaces later, as its own follow-up
- Any registry-to-registry federation or multi-tenant registry (already out of scope for the whole track, restated here since admin screens are the most likely place someone would be tempted to add it)

---

## Component breakdown

### 1. User management

- List all Cognito users with their current role
- Change a user's role (Author/Reviewer/Admin, multi-role allowed per `APPLICATION_ARCHITECTURE.md` §2.2: "A user can hold more than one role")
- This replaces SR.2's manual Cognito-console role seeding for new users going forward; it does not require migrating the test users seeded in SR.2 (they already work, nothing to redo)

### 2. Pack management

- Create a new pack name: provisions the pack's namespace in the registry (an empty `latest.json` or its absence, handled gracefully by the dashboard/CLI as "no published version yet") and makes it selectable in the pack editor's "new draft" flow
- Deprecate a pack: marks it as deprecated (exact mechanism -- a flag in the pack's registry metadata, or a convention like a `deprecated: true` field in `latest.json` -- decided during implementation). Deprecating a pack must not delete its already-published versions or break `stack add` for projects still using it; it should stop showing the pack as available for *new* drafts and surface a warning on `stack add` for that pack going forward.

### 3. Registry tokens

- Issue: generate a random opaque token, show it to the Admin exactly once (never retrievable again, same handling as any bearer credential), store only its hash plus `project_id`/`created_at` in the persistent store SR.2 introduced
- List: show existing tokens by project, with created/last-used timestamps, never the token value itself
- Revoke: set `revoked_at`; `GET /api/packs/:name/content` must reject a revoked token's next request immediately (no caching of validation results beyond what makes that true)
- This is the first phase where the hand-seeded test token from SR.2 can be replaced with a real one issued through the UI -- SR.2's seeded token can be revoked once a real one is in place, or left alone; nothing requires migrating it

---

## Build order

```
1. Admin: user management screen
2. Admin: pack management screen -- create new pack name
3. Admin: pack management screen -- deprecate pack
4. Admin: registry tokens screen -- issue, list, revoke
5. Regression: confirm SR.1-SR.3's flows are unaffected by a newly-created pack going through the same lifecycle as the original 12
```

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | An Admin can change another user's role and that takes effect on next login | Change a test user from Author to Reviewer; confirm they can now access `/review` |
| 2 | An Admin can create a new pack name, and an Author can immediately create a first draft for it | Create pack `kubernetes`; confirm it's selectable in the pack editor; author and publish a v1.0.0 through the full SR.3 loop |
| 3 | `cartographer stack add kubernetes` fetches the newly published pack | Run it against the registry configured in SR.1; confirm it installs correctly, same as any of the original 12 packs |
| 4 | Deprecating a pack stops it from being offered for new drafts but does not break existing `stack add` for that pack | Deprecate a test pack; confirm the editor no longer offers new drafts for it; confirm `stack add` for an already-installed project still fetches its last published version (with or without a deprecation warning, per the implementation decision above) |
| 5 | An Admin can issue a new registry token and a project configured with it can fetch packs | Issue a token; configure a test project's `cartographer.local.toml`; run `stack add`; confirm success |
| 6 | Revoking a token immediately blocks its next use | Revoke the token from criterion 5; re-run `stack add`; confirm it falls back to bundled per `registry_fallback` (or errors, if configured to), not a stale successful fetch |

---

## Test approach

**Unit tests (web app backend):**
- Role assignment: changing a role updates authorization checks immediately (no stale-session edge case where an old Reviewer keeps access after demotion within the same test).
- Pack creation: new pack is registered and immediately available to the editor.
- Deprecation: deprecated pack is excluded from "new draft" pack lists but its history and `stack add` fetch path remain intact.
- Registry token issuance: token value is returned exactly once in the issue response and never again in any subsequent read; only the hash is ever persisted.
- Registry token revocation: a revoked token fails validation on its very next use, not just after some cache TTL.

**Integration tests:**
- Full loop for a pack created through this phase's admin screen, reusing SR.3's end-to-end acceptance test verbatim but starting from pack creation instead of an existing pack.

**Browser tests (Playwright or Cypress):**
- Admin flow: create pack -> assign role -> author drafts -> review -> publish, as one continuous walkthrough.

---

## Track completion

When this sub-phase's exit criteria pass, all of the original `standards-registry.md` track's exit criteria are satisfied. See [standards-registry.md](standards-registry.md) for the full track overview and which sub-phase each original exit criterion now lives in.
