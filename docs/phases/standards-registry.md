# Standards Distribution Track: Registry and Web App

## Goal

An SME authors a new version of a standards pack in the web app, it passes review, and a project's next `cartographer stack add` picks it up -- with no CLI release and no PR to the Cartographer repository.

This track runs independently of Phase 1, 2, and 3. It is a packaging and authoring concern, not a KG/VDB concern. It can start after Phase 1 is stable and the three blocking open questions (OQ-08, OQ-09, OQ-10) are resolved.

**Entry condition:** Phase 1 is complete. OQ-08 (registry storage), OQ-09 (web app auth and review model), and OQ-10 (CLI fallback behavior) are resolved.

---

## References

| Document | What to read |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Section 6: standards distribution phasing |
| [APPLICATION_ARCHITECTURE.md](../APPLICATION_ARCHITECTURE.md) | Part 2: web app screen inventory, user roles, pack version lifecycle |
| [components/standards-packs.md](../components/standards-packs.md) | Pack structure, versioning, current bundled distribution |
| [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) | OQ-08, OQ-09, OQ-10: must be resolved before this track starts |

---

## Scope

### In scope

| Component | What ships |
|---|---|
| Standards Registry (S3) | Versioned S3 bucket; immutable pack version objects; CloudFront CDN for distribution |
| Standards web app | ECS Fargate + ALB; Cognito auth; authoring, review, and publish flows |
| CLI registry fetch | `stack add` and `init` fetch from registry; fall back to bundled on failure |
| CLI fallback behavior | Configurable via `stacks.registry_fallback` (`warn` or `error`) per OQ-10 |
| Pack version schema | Version object format stored in S3; readable by CLI |

### Explicitly out of scope

- Migrating existing bundled packs to the registry automatically (done manually as a one-time task)
- Registry-to-registry federation or multi-tenant registry
- CLI authoring tools (the web app is the authoring interface)

---

## Component breakdown

### 1. Standards Registry (S3)

**Infrastructure (AWS reference deployment):**
- S3 bucket with versioning enabled
- Bucket policy: public read for published objects; write restricted to the web app's IAM role
- CloudFront distribution in front of S3 for low-latency global reads
- Object key structure: `packs/<pack-name>/<version>/standards.md`
- Index object: `packs/<pack-name>/latest.json` -- points to the latest published version

**Pack version object format:**

```json
{
  "pack":        "python",
  "version":     "2.2.0",
  "published_at": "2026-09-24T10:00:00Z",
  "published_by": "a.patel@example.com",
  "changelog":   "Added async section; updated testing conventions.",
  "content_url": "https://cdn.example.com/packs/python/2.2.0/standards.md"
}
```

`latest.json` for each pack:

```json
{
  "pack":    "python",
  "version": "2.2.0",
  "url":     "https://cdn.example.com/packs/python/2.2.0/standards.md"
}
```

---

### 2. Standards web app

**Infrastructure:**
- ECS Fargate task running the web app container
- Application Load Balancer (ALB) in front of ECS
- Cognito user pool for authentication (user pools for Author, Reviewer, Admin roles)
- DynamoDB or RDS for draft state, review records, and version index (resolve per OQ-09)
- S3 write access via IAM role assigned to the ECS task (for publish operations)

**Screens and flows to implement** (full detail in [APPLICATION_ARCHITECTURE.md Part 2](../APPLICATION_ARCHITECTURE.md)):

| Screen | Status |
|---|---|
| Login (`/login`) | Cognito hosted UI or embedded form |
| Dashboard (`/`) | Pack list, latest versions, draft counts |
| Pack detail (`/packs/:packName`) | Published content, active draft, version history link |
| Pack editor (`/packs/:packName/drafts/:draftId/edit`) | Split-pane markdown editor, diff toggle, submit for review |
| Review queue (`/review`) | Drafts in IN REVIEW state |
| Review screen (`/review/:draftId`) | Side-by-side diff, inline comments, approve/reject |
| Publish confirmation (modal) | Confirm publish or defer |
| Version history (`/packs/:packName/versions`) | All published versions, diff between any two |
| Admin: user management (`/admin/users`) | Role assignment |
| Admin: pack management (`/admin/packs`) | Create new pack names, deprecate packs |

**Pack version lifecycle** (full state machine in [APPLICATION_ARCHITECTURE.md](../APPLICATION_ARCHITECTURE.md)):
```
DRAFT -> IN REVIEW -> APPROVED -> PUBLISHED
                  \-> REJECTED -> DRAFT (revised)
```

**Publish operation:**
- Triggered after a Reviewer approves and confirms publish
- Web app writes `standards.md` to `s3://packs/<name>/<version>/standards.md`
- Web app writes/updates `s3://packs/<name>/latest.json`
- State transitions to PUBLISHED; record is immutable from this point

---

### 3. CLI registry fetch (update to `stack add` and `init`)

**Changes to `cartographer stack add`:**
1. If `stacks.registry_url` is configured: fetch `<registry_url>/packs/<name>/latest.json`
2. Parse the version and `content_url`
3. Fetch `standards.md` from `content_url`
4. If fetch succeeds: write to `.claude/standards/<name>/standards.md`; record fetched version
5. If fetch fails:
   - `stacks.registry_fallback = "warn"` (default): log warning with URL and error; use bundled version
   - `stacks.registry_fallback = "error"`: exit `1` with error message
6. If `stacks.registry_url` is not configured: use bundled version (current behavior, unchanged)

**Changes to `cartographer init`:**
- Same registry fetch logic applies when `--stack <name>` is passed
- Bundled version is always the fallback

**Config additions:**

```toml
[stacks]
registry_url = "https://cdn.example.com"        # URL of the Standards Registry CDN
registry_fallback = "warn"                       # "warn" or "error" on registry fetch failure
```

**Reference:** [CONFIGURATION.md](../CONFIGURATION.md), [components/cli.md: stack add](../components/cli.md)

---

## Build order

```
1. Resolve OQ-08 (registry storage), OQ-09 (auth model), OQ-10 (fallback behavior)
2. Provision S3 bucket and CloudFront distribution (infrastructure)
3. Define pack version object schema (JSON schema document)
4. Publish first pack versions manually to S3 (python, react, cross-stack current versions)
5. CLI registry fetch (stack add + init updates)
6. CLI regression test: registry unreachable falls back to bundled correctly
7. Web app: Cognito setup + auth screens
8. Web app: dashboard + pack detail (read-only views)
9. Web app: pack editor (draft create/edit)
10. Web app: review queue + review screen
11. Web app: publish flow (writes to S3)
12. Web app: admin screens
13. End-to-end test: author -> review -> publish -> CLI picks up
```

---

## Open questions to resolve before starting

| Question | Blocks |
|---|---|
| OQ-08: Registry storage (S3 vs R2 vs MinIO) | Infrastructure provisioning (step 2) |
| OQ-09: Web app auth and review model (one vs two approvals; role assignment) | Cognito setup; review screen spec |
| OQ-10: CLI fallback behavior (`warn` vs `error`) | `stack add` and `init` implementation (step 5) |

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | An SME can log into the web app, create a draft version of the Python pack, and submit it for review | Walk through the author flow end to end |
| 2 | A Reviewer can view the draft, add a comment, and approve it | Walk through the review flow end to end |
| 3 | After approval, the Reviewer publishes the new version to the Standards Registry | Confirm the pack object appears in S3 with the correct key and `latest.json` is updated |
| 4 | `cartographer stack add python` on a project with `stacks.registry_url` configured fetches the newly published version | Run `stack add python`; inspect `.claude/standards/python/standards.md`; confirm it contains the content from the published version |
| 5 | `cartographer stack add python` when the registry is unreachable falls back to the bundled version and logs a warning | Block the registry URL; run `stack add python`; confirm bundled version is installed and warning is printed |
| 6 | `cartographer init --stack python` with registry configured fetches from the registry | Run `init`; confirm fetched version is written, not the bundled version |
| 7 | A published version is immutable: editing a published version in the web app is not possible | Attempt to edit a published version in the UI; confirm the editor is read-only |
| 8 | Version history shows all published versions with correct metadata | Navigate to `/packs/python/versions`; confirm all published versions appear in order |

---

## Test approach

### Web app tests

**Unit tests** (web app backend):
- Pack version state machine transitions: each valid and invalid transition
- Publish operation: correct S3 key structure; `latest.json` update; state set to PUBLISHED
- Auth middleware: Author cannot approve their own draft; cross-role access returns 403

**Integration tests** (web app + S3):
- Create draft -> submit -> approve -> publish; verify S3 objects exist with correct content
- Fetch `latest.json` after publish; verify version and URL are correct

**Browser tests** (Playwright or Cypress):
- Author flow: login -> create draft -> edit -> submit for review
- Review flow: login as Reviewer -> open review queue -> approve -> publish
- Read-only verification: published version editor is disabled

### CLI registry fetch tests

**Unit tests:**
- Registry URL configured + successful fetch: correct version installed
- Registry URL configured + fetch fails + `registry_fallback = "warn"`: bundled version installed, warning logged
- Registry URL configured + fetch fails + `registry_fallback = "error"`: exit `1`
- Registry URL not configured: bundled version installed, no network call made

**Integration tests:**
- Mock S3 endpoint (using a local HTTP server or LocalStack): full `stack add` flow against a real-shape response

### End-to-end acceptance test

```
1. Author logs into the web app
2. Creates a new draft of the Python pack with a recognizable change
   (add a distinctive line to standards.md)
3. Submits for review
4. Reviewer logs in, reviews, and approves
5. Reviewer publishes
6. Run: cartographer stack add python  (registry_url configured)
7. Open .claude/standards/python/standards.md
8. Confirm the distinctive line from step 2 is present
```

Pass criterion: step 8 confirms the published content is present. The entire loop from authoring to CLI delivery is verified.

---

*For the current bundled pack distribution, see [components/standards-packs.md](../components/standards-packs.md). For web app screen flows, see [APPLICATION_ARCHITECTURE.md Part 2](../APPLICATION_ARCHITECTURE.md).*
