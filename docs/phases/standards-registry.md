# Standards Distribution Track: Registry and Web App

## Goal

An SME authors a new version of a standards pack in the web app, it passes review, and a project's next `cartographer stack add` picks it up -- with no CLI release and no PR to the Cartographer repository.

This track runs independently of Phase 1, 2, and 3. It is a packaging and authoring concern, not a KG/VDB concern.

**Entry condition:** Phase 1 is complete (satisfied). OQ-08, OQ-09, and OQ-10 resolved (satisfied, 2026-10-05 -- see [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) closed questions). The track is unblocked; see the sub-phase table below for where implementation actually starts.

---

## Alignment check (2026-10-05)

Audited this document against the current codebase before any implementation work, per the project's standard practice of re-verifying phase-doc assumptions rather than trusting them at face value. Findings:

- **Confirmed accurate, unchanged:** `APPLICATION_ARCHITECTURE.md` Part 2 (screen inventory, roles, pack version lifecycle) still matches this document's design.
- **Changed 2026-10-05 (after this audit):** the web app's compute target moved from ECS Fargate to EKS, so it's deployable on Kubernetes -- see `ARCHITECTURE.md` §7.3's rationale note. AWS managed services (Cognito, S3) are unchanged; only the orchestration layer changed. `components/standards-webapp.md` and SR.2's infrastructure section are updated to match. Persistent state (registry tokens, and from SR.3 draft/review records) was later decided to be Postgres -- the same instance the central VDB backend already uses -- rather than DynamoDB, specifically to avoid a second stateful service; see `ARCHITECTURE.md` §7.3's Postgres rationale note.
- **Changed 2026-10-05, more significant (after the EKS change, reviewed by Hendrick):** the original design had the CLI fetch pack content directly from a public-read S3 bucket via CloudFront, with no request-level authentication -- anyone with a pack's URL could read it, with no way to audit or restrict access. Fixed: S3 is now private; every read (CLI and web app UI alike) goes through the web app's own authenticated API (`GET /api/packs/:name/content`), gated by a per-project bearer token for the CLI (same pattern as `promotion_token`). This reordered the sub-phases below -- CLI registry fetch moved from SR.1 to SR.2, since it now depends on the web app's API existing, not just S3. See `ARCHITECTURE.md` §7.2's correction note and `components/standards-webapp.md` §6-7, 9, 11.
- **Fixed:** `components/standards-packs.md` and `CONFIGURATION.md`'s `[stacks]` comment both documented only 2 bundled packs (`python`, `react`); the CLI actually bundles 12 (`cross-stack`, `python`, `react`, `typescript`, `golang`, `rust`, `java`, `kotlin`, `angular`, `vue`, `swift`, `dart`, per `stack.py`'s `KNOWN_PACKS`). Both docs corrected -- this matters for SR.1's bundled-pack migration step, which migrates 12 packs, not 2.
- **Fixed (more significant):** `components/cli.md`'s `stack add` section described the registry-fetch-with-fallback logic as *already shipped, current* `stack add` behavior. It is not -- `stack.py` has no registry-fetch code as of this writing; packs are always resolved from the bundled install. Corrected to describe current (bundled-only) behavior with a "planned, not yet implemented" pointer back to this track; SR.1 is where that note gets removed.
- **Fixed (broader, found in the same pass):** `CONFIGURATION.md`, `cartographer.example.toml`, `DATA_MODEL.md`, and `OPEN_QUESTIONS.md` had significant unrelated config documentation drift -- stale `[vdb]`/`[kg]`/`[embedder]`/`[ingestion]`/`[recall]`/`[registry]` sections that `config.py` never reads, a fabricated generic env-var derivation rule, a `doctor` validation list that didn't match `doctor.py`, and a per-machine registry documented as a configurable SQLite `.db` when it's actually a hardcoded JSON file. All corrected 2026-10-05, predates and is unrelated to this track, but was blocking an accurate read of what's real vs. planned.
- **Investigated and ruled out:** the screen table in this document included "Publish confirmation (modal)" which `APPLICATION_ARCHITECTURE.md`'s §2.4 screen inventory table omits. Not a real discrepancy -- that table only lists routable screens (it has a Path column), and the modal is documented in §2.5's flows. No action needed.
- **OQ-08/09/10 resolved 2026-10-05** specifically to unblock writing concrete sub-phase docs instead of leaving fetch/auth/fallback behavior as "TBD, see open question" in every sub-phase. See [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) closed questions for the decisions and rationale.

---

## References

| Document | What to read |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Section 6: standards distribution phasing |
| [APPLICATION_ARCHITECTURE.md](../APPLICATION_ARCHITECTURE.md) | Part 2: web app screen inventory, user roles, pack version lifecycle |
| [components/standards-packs.md](../components/standards-packs.md) | Pack structure, versioning, current bundled distribution (12 packs) |
| [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) | OQ-08, OQ-09, OQ-10: resolved 2026-10-05, see closed questions |
| [CONFIGURATION.md](../CONFIGURATION.md) | `[stacks]` section -- `registry_url`/`registry_fallback` are added to the schema in SR.2, not before (SR.1 has no CLI changes at all) |

---

## Scope

### In scope

| Component | What ships | Sub-phase |
|---|---|---|
| Standards Registry (S3, private) | Versioned S3 bucket, no public access; immutable pack version objects (zip + metadata); admin publish script for bootstrap/migration | SR.1 |
| Standards web app: auth + read views + registry API | Cognito; login, dashboard, pack detail, version history; `GET /api/packs/:name/content` (bearer-token authenticated) | SR.2 |
| CLI registry fetch | `stack add` and `init` fetch via the authenticated API; fall back to bundled on failure (`stacks.registry_fallback`, OQ-10) | SR.2 |
| Standards web app: authoring, review, publish | Pack editor, review queue/screen (one-approval, OQ-09), publish flow | SR.3 |
| Standards web app: admin | User management, pack management, registry token issuance/revocation | SR.4 |
| Per-project forks | A project can fork a pack into its own namespace in the registry and push local edits to it via the CLI, diverging from the global baseline | SR.5 |

### Explicitly out of scope (the whole track)

- Migrating existing bundled packs to the registry via anything other than a one-time manual/scripted task (SR.1) -- not automated, not repeated
- Registry-to-registry federation or multi-tenant registry **except the specific, narrow form added in SR.5** (per-project forks of individual packs, opt-in, CLI-push-only, no review gate) -- this line originally ruled out multi-tenancy entirely; SR.5 reopened it by explicit request on 2026-10-06, deliberately, not as scope creep discovered mid-implementation
- CLI authoring tools (the web app is the authoring interface) -- still true for the global baseline; SR.5's `stack push` is a narrow exception for a project's own fork, not a general authoring tool
- Per-pack author/reviewer assignment -- OQ-09's resolved decision is global roles

---

## Sub-phases

| Pass | Document | Scope | Entry condition |
|---|---|---|---|
| SR.1 | [sr-1-registry-infrastructure.md](sr-1-registry-infrastructure.md) | Private S3 registry infrastructure, pack version schema, bundled-pack migration via a throwaway admin script. No CLI or web app changes -- nothing here is network-reachable outside an operator's own AWS credentials. | **Complete 2026-10-05.** Bucket live at `cartographer-standards-registry-983883745126` (`us-east-1`), all 12 packs migrated, all exit criteria verified against the real bucket. |
| SR.2 | [sr-2-webapp-auth-and-read-views.md](sr-2-webapp-auth-and-read-views.md) | Web app: Cognito auth, login, dashboard, pack detail, version history (read-only); the authenticated `GET /api/packs/:name/content` endpoint; and CLI registry fetch (`stack add`/`init --stack`) against it | SR.1 complete |
| SR.3 | [sr-3-webapp-authoring-and-publish.md](sr-3-webapp-authoring-and-publish.md) | Web app: pack editor, review queue/screen, publish flow -- closes the full authoring loop | SR.2 complete. **Complete 2026-10-06.** |
| SR.4 | [sr-4-webapp-admin.md](sr-4-webapp-admin.md) | Web app: user management, pack management (create/deprecate pack names), registry token issuance/revocation | SR.3 complete. **Complete 2026-10-06.** |
| SR.5 | [sr-5-project-forks.md](sr-5-project-forks.md) | Per-project forks: a project copies a pack into its own registry namespace and pushes local edits to it via the CLI, opt-in, no review gate | SR.4 complete. **Complete 2026-10-06.** Added after the original track scope was set, by explicit request -- see the sub-phase doc's "Design decisions" section. |

**Why this order:** SR.1 is fully independent and provable without any web app or any network-reachable fetch path -- it proves the registry schema using a throwaway admin publish script, nothing more. SR.2 is now where the web app's API and CLI fetch are both built together, since CLI fetch requires that authenticated API to exist (it cannot be tested against raw S3 anymore -- see the alignment check above). SR.3 is where the track's actual goal is demonstrated end to end. SR.4 is pure management tooling around an already-working loop -- including the registry tokens SR.2 had to hand-seed -- and carries the least risk, so it's last among the originally-scoped sub-phases. SR.5 came after the original four and depends on SR.2's content API and SR.4's token model both already existing -- it reuses the project-scoped bearer token unchanged.

### Exit criteria

**Complete 2026-10-06: all five sub-phases pass.** See each sub-phase document for its own detailed exit criteria and test approach -- they are not duplicated here. The track's single most important exit criterion (SR.3's end-to-end acceptance test: author → review → publish → CLI delivery, demonstrated live) is the same goal stated at the top of this document. The one item not yet done is deploying to the org's actual shared EKS cluster (this environment only proved it against Docker Desktop's local Kubernetes / a plain local process) -- see SR.2's status note; this is an infra/ops step, not a remaining functional gap in the track itself.

---

*For the current bundled pack distribution, see [components/standards-packs.md](../components/standards-packs.md). For web app screen flows, see [APPLICATION_ARCHITECTURE.md Part 2](../APPLICATION_ARCHITECTURE.md).*
