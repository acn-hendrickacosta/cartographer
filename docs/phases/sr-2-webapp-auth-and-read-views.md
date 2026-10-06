# Standards Registry Pass SR.2: Web App -- Auth, Read Views, and CLI Registry Fetch

## Goal

An SME can log into the Standards web app and see the real, currently-published pack versions -- the ones SR.1 published via the admin script -- without yet being able to author or publish anything. Separately, `cartographer stack add`/`init --stack` can fetch a published pack version through this same application's authenticated API, using a per-project bearer token. Both are read-only; nothing here writes to S3.

**Rescoped 2026-10-05** to include CLI registry fetch, which was originally SR.1's job. Corrected after review: the original design had the CLI fetch pack content directly from a public-read S3 bucket via CloudFront, with no request-level authentication. Fixed by making S3 private (SR.1) and serving all reads -- CLI and web app UI alike -- through this application's own authenticated API. That means CLI fetch can't be built or tested until this phase's API exists, so it moved here from SR.1. See `ARCHITECTURE.md` §7.2's correction note and `components/standards-webapp.md` §6-7.

**Entry condition:** SR.1 complete (pack versions exist in S3, published via the admin script).

**Status as of 2026-10-05: substantially complete, verified against real infrastructure, not mocked.** What exists and was proven for real:

- **Real AWS resources** (account `983883745126`, `us-east-1`): a Cognito User Pool (`us-east-1_4TI3BpY8r`) with Hosted UI domain, an app client configured for the authorization-code flow, three groups (Author/Reviewer/Admin) with one seeded test user each; a `registry_tokens` table in Postgres (`cartographer_webapp` database, same instance as the central VDB backend -- see below) with one seeded test token. See `webapp/README.md` for the full resource list.
- **Backend application** (`webapp/backend/`, FastAPI): Cognito ID token verification via JWKS, the hosted-UI OAuth2 redirect/callback flow, session cookies, a JSON API (`/api/me`, `/api/packs`, `/api/packs/:name/:content_type`, `/api/packs/:name/:content_type/versions`) reading from SR.1's real S3 bucket, and `GET /api/packs/:name/content/:content_type` validating the bearer token against Postgres and returning the pack's zip from S3. 32 unit/API tests, against mocked boto3/psycopg2 (`webapp/backend/tests/`).
- **Frontend application** (`webapp/frontend/`, React + Vite SPA, built into `webapp/backend/app/static/dist/`): sidebar navigation with Standards/Skills/Agents as top-level destinations (not in-page tabs), matching `cartographer ui`'s own Explore/Registry/Stats sidebar pattern. Client-side routing via `react-router-dom` -- navigating between sidebar sections or packs issues only a `fetch()` call, never a full page reload. **Rebuilt 2026-10-05** from an earlier server-rendered Jinja2 version that was flagged in review as both slow (full page reload per click) and structurally wrong (standards/skills/agents nested as in-page tabs instead of sidebar destinations); see the browser-verification note below for what was re-confirmed after the rebuild.
- **Content scope extended 2026-10-05** to cover all three artifact types `cartographer stack add` installs -- standards, skills, agents -- not just standards, per explicit decision (previously assumed out of scope without ever being discussed). A 13th registry pack, `"core"`, was added for the cross-cutting skills/agents every stack pack gets alongside its own (mirrors `stack.py`'s `apply_pack()`, which already applied `("core", <stack name>)` for skills/agents, just not for the registry). Skills archives preserve one level of `<skill-name>/` nesting (required for Claude Code to auto-load them); standards and agents are flat. See `cartographer/standards_registry.py` and `webapp/backend/app/s3_registry.py`'s module docstrings for the full design, and `RegistryContentNotFoundError` for why a pack simply lacking one content type (e.g. "angular" has no stack-specific agents) is a silent fallback, not a logged warning.
- **End-to-end proof, run manually against the live resources above:** a real Cognito ID token (obtained via `AdminInitiateAuth`) verified correctly through the app's actual `verify_id_token`, extracting the right email and group; the dashboard, pack detail, and version history routes hit on a locally-running instance of the real server, rendering real S3 content for all 12 packs; the content endpoint's 401 (missing/invalid token), 401-after-revocation, and 200 paths all confirmed with real `curl`; and -- the actual point of this whole redesign -- a real `cartographer stack add`/`init --stack` run, from the actual CLI, fetching a real pack through this real authenticated server and writing correct content to disk.
- **A real bug found and fixed along the way:** `init.py` rebuilt `cartographer.toml` from scratch on every run, silently discarding any field it didn't explicitly special-case (previously only `topology.mode` was preserved across re-runs) -- so a project's `registry_url` vanished the moment someone re-ran `cartographer init`. Fixed to preserve the full existing config and override only what `init` actually owns. Caught by running the real re-run scenario, not by a mock. Regression test added (`cli/tests/test_init.py::test_init_rerun_preserves_fields_it_does_not_own`).

**Also browser-verified (2026-10-05, via Chrome DevTools MCP against the live local server):** the full interactive login loop -- Cognito hosted-UI form → real credential submit → redirect to `/auth/callback` → session set → app load -- plus sidebar navigation between Standards/Skills/Agents, pack detail (python's 11 real standards files, and separately its 6 skills with `<skill-name>/SKILL.md` nesting rendered correctly), version history, direct deep-link navigation (pasting a URL like `/skills/python/versions` directly, exercising the backend's SPA catch-all route), and logout -- all by clicking through an actual browser, not curl. Network-request inspection during this pass confirmed sidebar clicks issue exactly one new `fetch()` call each, no document reload. This caught three real bugs along the way: `hosted_ui_login_url()`/`hosted_ui_logout_url()` built the Cognito authorize/logout URLs by raw string interpolation instead of `urllib.parse.urlencode`; a separate `update-user-pool-client` call (made earlier to enable admin auth for token-verification testing) had silently wiped the app client's `CallbackURLs`/`AllowedOAuthFlows` -- Cognito's update API replaces the full OAuth config rather than merging, so any call omitting those fields resets them; and the first Vite build doubled the asset path to `/assets/assets/...` because `base: '/assets/'` was combined with Vite's own default `assets/` output subdirectory. All three fixed; the Cognito one is a real lesson for `webapp/README.md`'s deployment steps (step 3's `update-user-pool-client` call must always include every OAuth-related flag together, never just the one being changed).

**Persistent state moved from DynamoDB to Postgres (2026-10-05), after explicit direction:** the registry-tokens store originally shipped on DynamoDB. Changed to Postgres -- a new `cartographer_webapp` database in the *same instance* the CLI's central VDB backend already uses locally (`cli/tests/docker-compose.yml`'s `ci-pgvector-1` container; a real RDS/Aurora instance in production) -- specifically to avoid running two different stateful services for what's simple relational state. The now-unused DynamoDB table was deleted. Verified for real against the live container: token validation, revocation, and restoration all re-confirmed via direct `docker exec ... psql` writes plus live server requests, matching the original DynamoDB-based verification exactly. See `webapp/backend/app/db.py` (lazily-initialized connection pool -- a module-level eager pool would make even pure-unit tests fail to import without Postgres reachable) and `app/tokens.py`.

**A second real bug found and fixed, this one a performance issue:** `GET /api/packs` originally issued a per-pack `GET latest.json` + 3×`HEAD` loop, sequentially, across all 13 packs -- up to 52 blocking S3 round-trips for one page load. This is what caused an explicit "everything loads super slow" complaint. Measured individual S3 call latency directly from this dev environment at ~0.8s each (a network-latency floor for this environment, not application code). Fixed to one bulk `list_objects_v2` listing (`list_registry_index`) plus concurrent `ThreadPoolExecutor`-dispatched `latest.json` fetches (`get_latest_many`) -- cut page-load time from a theoretical 40+ seconds to a measured ~2 seconds (bounded by ~2 round-trip-times instead of 52). Expected to be a non-issue once deployed in-region/in-VPC on the real EKS cluster, where S3 latency is typically single-digit milliseconds.

**Not done:**
- **Deployment to the actual shared EKS cluster.** This environment only has `kubectl` access to Docker Desktop's local Kubernetes, not the org's real cluster. Manifests are written (`webapp/k8s/`) and ready, but applying them, wiring up the real IRSA role (now S3-only -- Postgres access is network/password-based, not IAM), and pointing a real hostname/Cognito callback URL at it are manual steps -- see `webapp/README.md`'s deployment section.
- SR.4's `/admin/registry-tokens` issuance UI -- the test token above was seeded directly into Postgres, same bootstrap pattern as the Cognito test users.

---

## Scope

### In scope

| Component | What ships |
|---|---|
| Infrastructure | EKS `Deployment` + `Service` + `Ingress` (AWS Load Balancer Controller) running the web app container; Cognito user pool with Author/Reviewer/Admin roles (role assignment itself is SR.4 -- for this phase, roles can be seeded manually in Cognito for test accounts) |
| Minimal persistent store | A `registry_tokens` table in Postgres -- the same instance the central VDB backend uses, in a separate `cartographer_webapp` database, decided 2026-10-05 over DynamoDB to avoid a second stateful service. Columns: `token_hash`, `project_id`, `created_at`, `revoked_at`. No draft/review schema yet -- that's SR.3, same database. |
| Frontend (React SPA) | Sidebar nav: Standards / Skills / Agents as top-level destinations, mirroring `cartographer ui`'s Explore/Registry/Stats pattern -- not in-page tabs on a single dashboard |
| Login (`/login`) | Cognito hosted UI; redirect to `/` on success, which the SPA then routes to `/standards` |
| Pack list (`/standards`, `/skills`, `/agents`) | Pack list filtered to packs that have published content of that type, with latest version. Draft counts don't exist yet (that's SR.3) and aren't shown at all in the rebuilt UI, rather than shown as placeholder dashes |
| Pack detail (`/:contentType/:name`) | Published content for that one content type (read-only) + link to version history. No "Edit / New draft" action yet -- that's SR.3 |
| Version history (`/:contentType/:name/versions`) | All published versions of that content type for a pack, with correct metadata |
| `GET /api/packs/:name/content/:content_type` | The CLI's fetch endpoint. Bearer-token authenticated; validates the token against the persistent store, reads the pack's latest version of that content type from S3 server-side, returns the zip archive with `X-Pack-Version` header. 401 on missing/invalid/revoked token, 404 if the pack has no published version of that type. |
| `GET /api/me`, `/api/packs`, `/api/packs/:name/:content_type`, `/api/packs/:name/:content_type/versions` | Session-cookie-authenticated JSON API consumed by the React SPA -- distinct from the CLI's bearer-token endpoint above |
| `stacks.registry_url` / `registry_fallback` config fields | Added to `StacksSection` in `config.py` |
| `registry_token` local override field | Added to `LocalOverrideConfig`; `CARTO_REGISTRY_TOKEN` env override, same pattern as `promotion_token`/`anthropic_api_key` |
| CLI registry fetch | `stack add` and `init --stack` call `GET /api/packs/:name/content/:content_type` once each for standards, and once each for ("core", `<stack name>`) for skills and agents; fall back to bundled per-type, per-pack-name, per `registry_fallback` |

### Explicitly out of scope (deferred to SR.3 / SR.4)

- Pack editor, review queue, review screen, publish flow
- Admin screens (user management, pack management, registry token issuance UI -- this phase seeds one test token by hand, same bootstrap pattern as Cognito test users)
- Any write path from the web app to S3 -- this phase is read-only end to end

---

## Component breakdown

### 1. Infrastructure

**Confirmed 2026-10-05: an EKS cluster already exists and is shared with other workloads.** This phase does not provision a cluster -- it onboards into the existing one:

- A dedicated namespace (e.g. `standards-webapp`) requested on the existing cluster, so RBAC, `ResourceQuota`/`LimitRange`, and `NetworkPolicy` scope to this app without touching other tenants on the shared cluster
- Web app packaged as a container image, deployed as a standard Kubernetes `Deployment` with a `Service` in front of it, inside that namespace
- `Ingress` resource, using whatever Ingress controller the existing cluster already runs (if it's the AWS Load Balancer Controller, an ALB is provisioned automatically; if the cluster uses a different controller, routing still works the same way -- nothing here is specific to ALB) -- TLS termination and routing happen at the Ingress, not inside the app
- `ServiceAccount` for the web app's pods, scoped to this namespace, with an IRSA role trust policy restricted to this specific namespace+ServiceAccount pair, granting read access to the SR.1 S3 bucket -- the app is the only thing in the EKS cluster that can reach it
- Cognito user pool. Role is stored as a Cognito custom attribute or group membership (Author/Reviewer/Admin, per `APPLICATION_ARCHITECTURE.md` §2.2). For this phase, seed 2-3 test users by hand (one per role) via the AWS console/CLI -- the Admin UI for managing this (`/admin/users`) doesn't exist until SR.4.
- Minimal persistent store for registry tokens, in Postgres (see Scope table) -- seed one test token by hand for this phase; `/admin/registry-tokens` self-service issuance is SR.4.

**Why Kubernetes (EKS), not ECS Fargate:** decided 2026-10-05 so the web app is deployable on Kubernetes rather than ECS-specific manifests, and specifically so it can ride on the org's existing EKS cluster rather than standing up new compute. Cognito and S3 stay as-is -- only the compute/orchestration layer changed. See `ARCHITECTURE.md` §7.3 for the full rationale. (Persistent state separately moved to Postgres instead of DynamoDB -- see the Scope table above and `ARCHITECTURE.md` §7.3's Postgres rationale note.)

### 2. Human-facing screens (React SPA, `webapp/frontend/`)

**Login** (`/login`): a plain backend redirect (not an SPA route) to the Cognito hosted UI. On success, Cognito redirects to `/auth/callback` (also backend, sets the session cookie), which redirects to `/`, which the SPA's router sends to `/standards`. On failure, the backend returns a 401 before any session is set.

**Sidebar**: Standards / Skills / Agents as top-level nav destinations -- not in-page tabs on a single dashboard, correcting the original (undiscussed) assumption that only standards content belonged in the registry at all, and a since-corrected first implementation that put all three as tabs within one "Packs" view. Matches `cartographer ui`'s own Explore/Registry/Stats sidebar pattern.

**Pack list** (`/standards`, `/skills`, `/agents`): list of pack names that have published content of that type, with latest version, read from each pack's `latest.json` in S3 (via the backend's `GET /api/packs?type=...`, never a raw S3 URL). No draft/review-queue placeholder columns -- that state doesn't exist until SR.3, and showing placeholder dashes for it in three separate list views would be more visual noise than value.

**Pack detail** (`/:contentType/:name`): the content for that one type -- standards/agents render as flat file cards; skills render as `<skill-name>/SKILL.md` cards, since a skills archive preserves that nesting. Link to version history. No "Edit / New draft" action yet -- that's SR.3.

**Version history** (`/:contentType/:name/versions`): every published version of that content type for the pack, in order, with `published_at`/`published_by`/`changelog` from each version's `version.json`.

### 3. CLI registry fetch (`GET /api/packs/:name/content/:content_type`)

**Server side (this phase, new):**
1. Validate the `Authorization: Bearer <token>` header against the token store (hash the incoming token, look up by hash, reject if not found or `revoked_at` is set).
2. Look up the pack's `latest.json` in S3 server-side (via the pod's IRSA role).
3. Read the corresponding `<content_type>.zip` from S3 (`standards`/`skills`/`agents` -- FastAPI validates the path segment against this `Literal`, 422 for anything else).
4. Return it with `Content-Type: application/zip` and an `X-Pack-Version` header. 404 if the pack has no published content of that type. 401 if the token is missing, unknown, or revoked.

**CLI side (`cartographer/standards_registry.py`, rewritten this phase):**
1. Load `stacks.registry_url` from `cartographer.toml` and `registry_token` from `cartographer.local.toml` (or `CARTO_REGISTRY_TOKEN`).
2. If `registry_url` is set but no token is configured: treat as a fetch failure immediately (don't bother making a request that can only 401) and apply `registry_fallback`.
3. `GET {registry_url}/api/packs/{name}/content/{content_type}` with the bearer token -- once for standards (pack name only), once each for skills and agents for both `"core"` and the stack's own pack name (mirrors `commands/stack.py`'s pre-existing bundled-install loop).
4. On `200`: extract into the right destination -- flat for standards/agents (`extract_pack_zip`), preserving `<skill-name>/` nesting for skills (`extract_skills_zip`).
5. A 404 specifically (`RegistryContentNotFoundError`) is always a silent fallback regardless of `registry_fallback` -- most (pack, content_type) pairs genuinely have no content (e.g. "angular" has no stack-specific agents), and that's not an operational problem worth a warning. Any other failure (401, network, malformed response) respects `registry_fallback`: "warn" logs and falls back, "error" exits 1.
6. If `registry_url` is not configured at all: bundled version, no network call (current/unchanged behavior for every project that hasn't adopted the registry).

**Config:**

```toml
[stacks]
active = ["python"]
registry_url = "https://standards.example.com"   # base URL of the web app's API
registry_fallback = "warn"                        # "warn" (default) or "error"
```

```toml
# cartographer.local.toml (gitignored)
registry_token = ""   # or CARTO_REGISTRY_TOKEN env var
```

---

## Build order

```
1. Build and verify the whole stack locally first (see "Local development and testing" below)
2. Request namespace + IRSA role on the existing EKS cluster (no cluster provisioning needed)
3. Deployment/Service/Ingress manifests, applied to that namespace
4. Minimal persistent store: registry_tokens table in Postgres (cartographer_webapp database) only
5. Cognito user pool + manually-seeded test users (one per role)
6. Backend: JSON API skeleton (/api/me, auth guard, session handling)
7. Backend: GET /api/packs/:name/content/:content_type -- token validation + S3 read + zip response
8. Seed one test registry token by hand
9. Frontend: React + Vite scaffold, sidebar nav (Standards/Skills/Agents), client-side routing
10. Frontend: pack list, pack detail, version history views, each calling the JSON API
11. CLI: registry_url/registry_fallback/registry_token config fields
12. CLI: rewrite standards_registry.py to call the authenticated endpoint for all three content types (standards once; skills/agents for "core" + stack name); wire into stack.py's apply_pack
13. CLI regression test: registry unreachable / token invalid both fall back to bundled correctly; a 404 for one content type falls back silently
```

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | A seeded test user can log in via Cognito and lands on the Standards view | Walk through login with each of the three role types |
| 2 | Each sidebar view (Standards/Skills/Agents) shows the real latest version for every pack published in SR.1 that has content of that type | Compare each view's contents against what SR.1's admin script actually published, including the `"core"` pack appearing only in Skills/Agents (it has no standards) |
| 3 | Pack detail renders the actual published content for a pack, correctly per content type | Open `/standards/python`, `/skills/python`, `/agents/python`; confirm content matches what was published, with skills showing `<skill-name>/SKILL.md` nesting |
| 4 | Version history lists every version published so far for that content type, correctly ordered | Publish a second version of one pack via SR.1's admin script; confirm it appears |
| 5 | `cartographer stack add python` with `registry_url` and a valid `registry_token` configured fetches standards, skills (core + python), and agents (core + python) | Run it; inspect `.claude/standards/python/`, `.claude/skills/`, `.claude/agents/`; confirm contents match what SR.1 published, not the bundled versions |
| 6 | `cartographer init --stack python` does the same | Same check, via `init` |
| 7 | Missing/invalid/revoked token + `registry_fallback = "warn"` (default) | Run `stack add python` with a bad token; confirm bundled versions installed for all three types, warning logged, exit `0` |
| 8 | Missing/invalid/revoked token + `registry_fallback = "error"` | Same, with `registry_fallback = "error"`; confirm exit `1` |
| 9 | `registry_url` unset | `stack add`/`init` use bundled versions; confirm no network call is attempted at all |
| 10 | A pack genuinely missing one content type (e.g. "angular" has no agents) falls back silently, no warning logged | Run `stack add angular` with a valid token and registry configured; confirm bundled agents installed with no warning text, since a 404 for a missing content type isn't a failure |
| 11 | No write path exists from the web app yet | Confirm there is no UI affordance anywhere in this phase that would write to S3 |
| 12 | A request to `/api/packs/:name/content/:content_type` with no `Authorization` header, or a revoked token, is rejected with 401 | Direct HTTP test against the endpoint, bypassing the CLI |
| 13 | Navigating between sidebar sections and packs never triggers a full page reload | Browser network-request inspection: confirm each click issues only `fetch()` calls (`/api/...`), no new `document` request |

---

## Test approach

### Local development and testing

Confirmed 2026-10-05: local development uses Docker Desktop's built-in Kubernetes (a single-node cluster). The whole stack -- except Cognito -- runs there before anything touches the shared EKS cluster:

| Dependency | Local stand-in | Notes |
|---|---|---|
| Kubernetes cluster | Docker Desktop Kubernetes | Same `Deployment`/`Service`/`Ingress` manifests as EKS, unchanged |
| Ingress controller | `ingress-nginx`, installed once via Helm | Docker Desktop's cluster doesn't ship one by default (EKS's AWS Load Balancer Controller is AWS-specific anyway) -- this is the only manifest-level difference between local and EKS, isolated to the `Ingress` resource's `ingressClassName` |
| S3 (registry storage, read server-side only) | LocalStack or MinIO container | Same pattern used in SR.1's admin-script tests; S3-compatible API, same client code, no app-level branching |
| Cognito | A real Cognito User Pool in a separate, low-cost dev AWS account | Cannot run locally or be meaningfully mocked without losing confidence in the actual JWT/auth flow under test. This is the one dependency worth reaching out to AWS for even during local dev. |
| IRSA (S3 access only) | Default AWS SDK credential chain (local AWS profile / env vars) | IRSA is just how that chain resolves specifically on EKS -- don't hardcode an IRSA-only credential path in app code; the SDK's default provider chain works unchanged in both places |
| Postgres (registry tokens, SR.3 draft/review state) | `cli/tests/docker-compose.yml`'s `ci-pgvector-1` container, same one the CLI's own central VDB integration tests use, in a separate `cartographer_webapp` database | Not IAM/IRSA -- network + `DATABASE_URL` password auth, same in both environments. Production points `DATABASE_URL` at a real RDS/Aurora instance instead of this container. |
| Registry token | A hand-seeded row in Postgres, same as production | No special local handling -- it's just app data |
| Frontend | `npm run dev` (Vite dev server, port 5173) proxying `/api`, `/login`, `/auth`, `/logout` to the backend running separately on `:8000` | Hot reload while editing `webapp/frontend/src/`. Production/local-non-dev runs serve the built `dist/` directly from the backend instead -- see `webapp/README.md`. |

Nothing here is thrown away once this ships against the real EKS cluster -- the same manifests, same app code, and same AWS SDK calls carry over; only the Ingress controller and credential source differ between local and EKS.

### Automated tests

**Unit tests (web app backend):**
- Token validation: valid token passes, unknown/revoked/missing token returns 401, each independently tested.
- `GET /api/packs/:name/content/:content_type`: happy path returns correct zip bytes and `X-Pack-Version` header; unpublished pack or missing content type returns 404; invalid content type returns 422.
- `GET /api/me`, `/api/packs`, `/api/packs/:name/:content_type`, `/api/packs/:name/:content_type/versions`: session-required, correct filtering/shape, skills flattened to `<skill-name>/<filename>` keys.
- `list_registry_index`/`get_latest_many`: the bulk-listing + concurrent-fetch functions that replaced the original per-pack GET+3×HEAD loop -- that sequential version was the actual cause of a real "everything loads super slow" complaint (up to 52 blocking S3 round-trips for one page load; fixed to 1 list + N concurrent gets).

**Unit tests (CLI, `cartographer/standards_registry.py` and `commands/stack.py`):**
- Registry URL + valid token + successful fetch: correct version installed, overwriting bundled content, for each of standards/skills/agents.
- Registry URL configured, no token set: treated as immediate failure (no network call), `registry_fallback` applies.
- Registry URL + token, server returns 401 (invalid/revoked): `registry_fallback` applies.
- Registry URL + token, server returns 404 (no published content of that type): silent fallback regardless of `registry_fallback` (`RegistryContentNotFoundError`) -- not a warning-worthy event, since most (pack, content_type) pairs genuinely lack one or more types.
- Registry URL + token, network error: `registry_fallback` applies.
- Registry URL not configured: bundled version, no network call made at all (mock/assert the HTTP client is never invoked).
- Skills extraction preserves `<skill-name>/` nesting; standards/agents extraction is flat; both reject path-traversal entries by construction (only the basename, or last two path components for skills, is ever used as the destination).

**Integration tests:**
- Real HTTP server (or the actual web app running locally per above) serving `/api/packs/:name/content/:content_type`; run the full `stack add` flow against it with a valid and then a revoked token, across all three content types.

**Browser tests (done by hand via Chrome DevTools MCP for this phase; no Playwright/Cypress suite yet):**
- Login flow, including the interactive Cognito hosted-UI form itself (not just the redirect URL).
- Sidebar navigation between Standards/Skills/Agents → pack detail → version history → back, confirmed via network-request inspection to be `fetch()`-only (no document reload).
- Direct deep-link navigation to a nested route (e.g. pasting `/skills/python/versions`) to exercise the backend's SPA catch-all.

---

*Next: [sr-3-webapp-authoring-and-publish.md](sr-3-webapp-authoring-and-publish.md) adds the write path -- draft, review, and publish -- that closes the full authoring loop.*
