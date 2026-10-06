# Component Spec: Standards Web App

The Standards web app is a separate application from the CLI and the plugin. It lets SMEs author, review, and publish standards pack content into the Standards Registry without needing repo access or a CLI release cycle.

This component is part of the standards distribution track, which is phased independently of Phase 1, 2, and 3, and broken into sub-phases SR.1-SR.4. The three blocking open questions (OQ-08, OQ-09, OQ-10) were resolved 2026-10-05 -- see [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) closed questions. See [phases/standards-registry.md](../phases/standards-registry.md) for the full implementation plan.

> This document is not the same as `cartographer ui`, which is a lightweight local knowledge browser built into the CLI for developers to inspect their own VDB and KG. See [components/cli.md](cli.md) for that command.

---

## 1. Purpose

Today, changing a standards pack requires a PR to the Cartographer repository and a CLI release. This means only developers with repo access can contribute standards, and any change takes a full release cycle to reach projects.

The Standards web app breaks this dependency. SMEs who know a stack well can author new pack content, have it reviewed, and publish it -- without touching the CLI codebase or waiting for a release.

---

## 2. What it is not

| Not this | What it is instead |
|---|---|
| A knowledge browser | That is `cartographer ui`, a local CLI command |
| Part of the CLI | A separate application with its own deployment |
| A replacement for the bundled packs | Bundled packs remain the fallback when the registry is unreachable |
| A code editor or IDE | It edits markdown standards content, not code |

---

## 3. User roles

| Role | Who | Permissions |
|---|---|---|
| Author | Subject matter expert | Create and edit draft pack versions; submit for review; view all published versions |
| Reviewer | Designated approver | Review drafts; approve or reject; publish approved drafts |
| Admin | Platform owner | Manage users and role assignments; create new pack names; deprecate packs |

A user may hold more than one role. An Author cannot approve their own draft.

---

## 4. Pack version lifecycle

```
DRAFT -> IN REVIEW -> APPROVED -> PUBLISHED
                  \-> REJECTED -> DRAFT (revised)
```

| State | Who controls the transition |
|---|---|
| DRAFT -> IN REVIEW | Author submits the draft |
| IN REVIEW -> APPROVED | Reviewer approves |
| IN REVIEW -> REJECTED | Reviewer rejects (must include a comment) |
| REJECTED -> DRAFT | Author revises and re-edits |
| APPROVED -> PUBLISHED | Reviewer confirms publish (may defer) |

A published version is immutable. Corrections require a new draft with a new version number.

---

## 5. Screen inventory

| Screen | Path | Role access |
|---|---|---|
| Login | `/login` | All |
| Dashboard | `/` | All |
| Pack detail | `/packs/:packName` | All |
| Pack editor | `/packs/:packName/drafts/:draftId/edit` | Author |
| Review queue | `/review` | Reviewer |
| Review screen | `/review/:draftId` | Reviewer |
| Version history | `/packs/:packName/versions` | All |
| Admin: user management | `/admin/users` | Admin |
| Admin: pack management | `/admin/packs` | Admin |
| Admin: registry tokens | `/admin/tokens` | Admin |

Added `/admin/tokens` 2026-10-05 alongside the CLI-fetch-goes-through-the-API correction -- an Admin needs somewhere to issue and revoke the per-project bearer tokens that gate `/api/packs/:name/content`. Full screen flows, wireframes, and navigation are documented in [APPLICATION_ARCHITECTURE.md: Part 2](../APPLICATION_ARCHITECTURE.md), updated to match.

---

## 6. Infrastructure (reference deployment: EKS)

| Concern | Service | Notes |
|---|---|---|
| Compute | Amazon EKS | Web app runs as a Kubernetes `Deployment` behind a `Service`; `HorizontalPodAutoscaler` for scale. Chosen 2026-10-05 so the web app is deployable on Kubernetes; see `ARCHITECTURE.md` §7.3 for the ECS-to-EKS rationale. |
| Load balancing | Kubernetes `Ingress` (AWS Load Balancer Controller) | Provisions an ALB from the `Ingress` resource; TLS termination, routes to the Service's pods. |
| Auth | Amazon Cognito | User pools for Author/Reviewer/Admin roles; JWT authorizer in front of the Ingress (or validated in-app) |
| Persistent state | PostgreSQL -- same instance as the central VDB backend, separate database (`cartographer_webapp`) | Per-project registry API tokens (SR.2, shipped); draft records, review state, published version index (SR.3). Decided 2026-10-05 over DynamoDB specifically to avoid a second stateful service alongside Postgres. |
| Pack storage | Amazon S3 (private) | Immutable published pack archives keyed by `packs/<name>/<version>/<content_type>.zip` (`content_type` is `standards`, `skills`, or `agents`, each independently optional per pack). No public access, no CDN in front of it -- see the correction note below. **SR.5 (2026-10-06):** a per-project fork lives at `projects/<project_id>/packs/<name>/fork/<content_type>.zip` -- same key shape, a separate prefix, a fixed marker version (`fork`) instead of a real semver. See §10. |

The web app writes to S3 via IRSA (IAM Roles for Service Accounts) -- a Kubernetes `ServiceAccount` annotated with an IAM role, the EKS-native equivalent of an ECS task IAM role. Reads also go through the app (§7 `GET /api/packs/:name/content/:content_type`), never directly from S3.

**Corrected 2026-10-05:** this section originally put a CloudFront CDN in front of a public-read S3 bucket, with the CLI fetching pack content directly from it -- no request-level authentication at all. That meant anyone with a pack's URL could read it, with no way to restrict or audit access. Removed. S3 is now private; every read (CLI or web app UI) goes through this application's own authenticated API.

---

## 7. API surface

The web app exposes a REST API consumed by both its own frontend (Cognito JWT auth) and the CLI (per-project bearer token auth). **Corrected 2026-10-05:** this section previously stated "the CLI does not call the web app API -- the CLI reads directly from the CloudFront/S3 distribution." That's reversed now -- see `/api/packs/:name/content` below, and the correction note in §6.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/packs` | GET | Cognito (All roles) | List all packs with latest published version |
| `/api/packs/:name` | GET | Cognito (All roles) | Pack detail: published content, active draft |
| `/api/packs/:name/content/:content_type` | GET | Bearer token (per-project) | **CLI's fetch endpoint.** Validates the token, reads the latest published version from S3 server-side, returns the zip archive directly (`Content-Type: application/zip`, `X-Pack-Version` response header). 401 if the token is missing/invalid, 404 if the pack has no published version of this content type. **SR.5:** if the calling project has forked this pack, serves the fork instead (`X-Pack-Version: fork`) -- transparent to the CLI, no config change needed. |
| `/api/packs/:name/fork` | POST | Bearer token (per-project) | **SR.5.** Copies the pack's current baseline into this project's own namespace. 409 if already forked, 404 if the pack has no published baseline. |
| `/api/packs/:name/fork/:content_type` | PUT | Bearer token (per-project) | **SR.5.** Pushes this project's current local content for one content type into its fork, wholesale-replacing what was there. 404 if no fork exists yet. |
| `/api/packs/:name/drafts` | POST | Cognito (Author) | Create a new draft |
| `/api/packs/:name/drafts/:id` | GET | Cognito (Author, Reviewer) | Get draft content and state |
| `/api/packs/:name/drafts/:id` | PATCH | Cognito (Author) | Update draft content (DRAFT state only) |
| `/api/packs/:name/drafts/:id/submit` | POST | Cognito (Author) | Submit for review (DRAFT -> IN REVIEW) |
| `/api/packs/:name/drafts/:id/approve` | POST | Cognito (Reviewer) | Approve (IN REVIEW -> APPROVED) |
| `/api/packs/:name/drafts/:id/reject` | POST | Cognito (Reviewer) | Reject with comment (IN REVIEW -> REJECTED) |
| `/api/packs/:name/drafts/:id/publish` | POST | Cognito (Reviewer) | Publish to S3 (APPROVED -> PUBLISHED) |
| `/api/packs/:name/versions` | GET | Cognito (All roles) | List all published versions |
| `/api/packs/:name/versions/:version` | GET | Cognito (All roles) | Get a specific published version's content |
| `/admin/users` | GET, POST, PATCH | Cognito (Admin) | User management |
| `/admin/packs` | GET, POST, PATCH | Cognito (Admin) | Pack management |
| `/admin/registry-tokens` | GET, POST, DELETE | Cognito (Admin) | Issue/revoke per-project bearer tokens for CLI access to `/api/packs/:name/content` |

---

## 8. Pack publish operation

When a Reviewer confirms publish, the web app:

1. Fetches the approved draft content from the database.
2. Writes `packs/<pack-name>/<version>/standards.md` to S3 (immutable; no overwrite).
3. Writes/updates `packs/<pack-name>/latest.json` with the new version metadata.
4. Updates the draft state to PUBLISHED in the database.
5. Returns success to the frontend.

If step 2 or 3 fails, the state is not updated to PUBLISHED and the operation may be retried.

---

## 9. Security

| Concern | Control |
|---|---|
| Authentication | Cognito JWT for the web app's own frontend; per-project bearer token for the CLI (`/api/packs/:name/content` only). All API endpoints require one or the other -- there is no unauthenticated endpoint. |
| Authorization | Role checked per endpoint; Author cannot approve own draft (enforced server-side, not only in UI) |
| Registry tokens | Opaque, randomly generated, stored hashed (not plaintext) in the persistent state store; scoped to a single project; revocable via `/admin/registry-tokens`; carry no role or human-user identity, only project scope |
| S3 access | Only the web app's pod ServiceAccount (via IRSA) may read or write the packs bucket; no pre-signed URLs issued to the CLI or browsers -- the app always reads/writes S3 itself and returns bytes, never a direct S3 link |
| Immutability | S3 object key includes the version number; overwriting a published version is prevented by S3 bucket policy |
| Secrets | Cognito client IDs, database credentials, and S3 bucket names in AWS Secrets Manager, synced into the cluster via the Secrets Store CSI driver (or loaded directly by the app at startup); never in application config files or plain Kubernetes `Secret` manifests committed to a repo |

---

## 10. Relationship to bundled packs

The Standards web app and the bundled packs in the CLI are independent distribution channels for the same content.

| Channel | How packs are updated | When to use |
|---|---|---|
| Bundled in CLI | PR to the Cartographer repo + CLI release | Cross-stack baseline; default content; fallback when registry is unreachable |
| Standards Registry (via web app) | Author -> review -> publish flow | Stack-specific updates; SME contributions without a CLI release |

When the registry is configured, the CLI fetches from it. When unreachable, the CLI falls back to bundled defaults. Both channels may contain different versions of the same pack; the registry version takes precedence when available.

---

## 10.5 Per-project forks (SR.5, 2026-10-06)

A third channel, narrower than the two above: a single project can fork a pack into its own
namespace in the registry (`projects/<project_id>/packs/<name>/fork/...`) and push local edits to
it directly via the CLI (`cartographer stack fork <pack>` / `stack push <pack>`), bypassing the
author/review/publish flow entirely -- the project's own bearer token is what gates who can push,
since there's no multi-user review needed for a project's own copy of its own content.

This is opt-in per project and per pack: a project's fetches hit the shared baseline exactly as
described above until that project explicitly forks a specific pack, at which point its fetches for
*that pack only* transparently prefer the fork (server-side, keyed off the same bearer token already
used for every fetch -- no CLI config change). Forking is one-time; re-forking an already-forked pack
is refused, and there's no "rebase onto newer baseline" operation -- picking up upstream changes into
an existing fork is a manual, project-side task. See `phases/sr-5-project-forks.md` for the full
design and verification record.

---

## 11. Open questions (resolved 2026-10-05)

| Question | Decision |
|---|---|
| OQ-08 | S3, with an S3-compatible interface documented so R2/MinIO can substitute later |
| OQ-09 | One approval required; any Reviewer other than the draft's own Author |
| OQ-10 | Warn and fall back to bundled by default (`stacks.registry_fallback = "warn"`); `"error"` available as opt-in |

See [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) closed questions for full rationale. Persistent state is Postgres (decided 2026-10-05, same instance as the central VDB backend) -- see `phases/sr-3-webapp-authoring-and-publish.md` and `ARCHITECTURE.md` §7.3.

---

*For the full screen flows and wireframes, see [APPLICATION_ARCHITECTURE.md: Part 2](../APPLICATION_ARCHITECTURE.md). For the phased implementation plan including build order, exit criteria, and test approach, see [phases/standards-registry.md](../phases/standards-registry.md).*
