# Component Spec: Standards Web App

The Standards web app is a separate application from the CLI and the plugin. It lets SMEs author, review, and publish standards pack content into the Standards Registry without needing repo access or a CLI release cycle.

This component is part of the standards distribution track, which is phased independently of Phase 1, 2, and 3. It does not ship until the three blocking open questions (OQ-08, OQ-09, OQ-10) are resolved. See [phases/standards-registry.md](../phases/standards-registry.md) for the full implementation plan.

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

Full screen flows, wireframes, and navigation are documented in [APPLICATION_ARCHITECTURE.md: Part 2](../APPLICATION_ARCHITECTURE.md).

---

## 6. Infrastructure (AWS reference deployment)

| Concern | Service | Notes |
|---|---|---|
| Compute | Amazon ECS Fargate | Containerized application; no server management |
| Load balancing | Application Load Balancer (ALB) | TLS termination; routes to ECS tasks |
| Auth | Amazon Cognito | User pools for Author/Reviewer/Admin roles; JWT authorizer on ALB |
| Persistent state | DynamoDB or RDS | Draft records, review state, published version index; choice per OQ-09 |
| Pack storage | Amazon S3 | Immutable published pack objects keyed by `packs/<name>/<version>/standards.md` |
| CDN | Amazon CloudFront | Serves S3 pack objects to CLI fetches globally |

The web app writes to S3 via an IAM role assigned to the ECS task. Developers and the CLI read from CloudFront. No direct S3 access for end users.

---

## 7. API surface

The web app exposes a REST API consumed by its own frontend. The CLI does not call the web app API -- the CLI reads directly from the CloudFront/S3 distribution.

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/packs` | GET | All | List all packs with latest published version |
| `/api/packs/:name` | GET | All | Pack detail: published content, active draft |
| `/api/packs/:name/drafts` | POST | Author | Create a new draft |
| `/api/packs/:name/drafts/:id` | GET | Author, Reviewer | Get draft content and state |
| `/api/packs/:name/drafts/:id` | PATCH | Author | Update draft content (DRAFT state only) |
| `/api/packs/:name/drafts/:id/submit` | POST | Author | Submit for review (DRAFT -> IN REVIEW) |
| `/api/packs/:name/drafts/:id/approve` | POST | Reviewer | Approve (IN REVIEW -> APPROVED) |
| `/api/packs/:name/drafts/:id/reject` | POST | Reviewer | Reject with comment (IN REVIEW -> REJECTED) |
| `/api/packs/:name/drafts/:id/publish` | POST | Reviewer | Publish to S3 (APPROVED -> PUBLISHED) |
| `/api/packs/:name/versions` | GET | All | List all published versions |
| `/api/packs/:name/versions/:version` | GET | All | Get a specific published version's content |
| `/admin/users` | GET, POST, PATCH | Admin | User management |
| `/admin/packs` | GET, POST, PATCH | Admin | Pack management |

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
| Authentication | Cognito JWT; all API endpoints require a valid token |
| Authorization | Role checked per endpoint; Author cannot approve own draft (enforced server-side, not only in UI) |
| S3 write access | Only the ECS task's IAM role may write to the packs bucket; no pre-signed upload URLs issued to browsers |
| Immutability | S3 object key includes the version number; overwriting a published version is prevented by S3 bucket policy |
| Secrets | Cognito client IDs, database credentials, and S3 bucket names in AWS Secrets Manager; never in application config files |

---

## 10. Relationship to bundled packs

The Standards web app and the bundled packs in the CLI are independent distribution channels for the same content.

| Channel | How packs are updated | When to use |
|---|---|---|
| Bundled in CLI | PR to the Cartographer repo + CLI release | Cross-stack baseline; default content; fallback when registry is unreachable |
| Standards Registry (via web app) | Author -> review -> publish flow | Stack-specific updates; SME contributions without a CLI release |

When the registry is configured, the CLI fetches from it. When unreachable, the CLI falls back to bundled defaults. Both channels may contain different versions of the same pack; the registry version takes precedence when available.

---

## 11. Open questions blocking this component

| Question | Detail |
|---|---|
| OQ-08 | Registry storage: S3, R2, or MinIO? |
| OQ-09 | Auth and review model: one or two approvals? DynamoDB or RDS for draft state? |
| OQ-10 | CLI fallback behavior when registry is configured but unreachable |

None of these block documenting the component. All three must be resolved before implementation begins.

---

*For the full screen flows and wireframes, see [APPLICATION_ARCHITECTURE.md: Part 2](../APPLICATION_ARCHITECTURE.md). For the phased implementation plan including build order, exit criteria, and test approach, see [phases/standards-registry.md](../phases/standards-registry.md).*
