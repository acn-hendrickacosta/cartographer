# Standards Web App

SR.2 slice (see [docs/phases/sr-2-webapp-auth-and-read-views.md](../docs/phases/sr-2-webapp-auth-and-read-views.md)): Cognito-authenticated Standards/Skills/Agents browsing, plus the CLI's authenticated `GET /api/packs/:name/content/:content_type` endpoint. No draft/review/publish (SR.3) or admin screens (SR.4) yet.

## Layout

```
webapp/
  backend/   FastAPI app: a JSON API (consumed by frontend/) plus the CLI's
             bearer-token content endpoint. Also serves the built frontend
             as static files.
  frontend/  React + Vite SPA. Source only -- build output is committed into
             backend/app/static/dist/ (same pattern as cli/ui-src ->
             cli/src/cartographer/ui/static) so the backend runs without
             Node/npm; only rebuild this if you change frontend/src/.
  k8s/       Kubernetes manifests for the existing shared EKS cluster.
```

**Rebuilt 2026-10-05** from server-rendered Jinja2 pages to this React SPA + JSON API split, for two reasons raised in review: the Jinja2 version caused a full page reload on every navigation click (slow), and it nested Standards/Skills/Agents as in-page tabs on a single "Packs" view rather than top-level sidebar destinations -- inconsistent with `cartographer ui`'s own Explore/Registry/Stats sidebar pattern. Confirmed via Chrome DevTools MCP network inspection that clicking between sidebar sections now triggers exactly one `fetch()` call, no document reload.

**Design matches `cartographer ui`'s "Ethereal Glass" system** (`cli/ui-src/src/style.css`) verbatim where it applies: same CSS variables, same sidebar/brand/nav structure, same glass-card/table/button components, Space Grotesk + JetBrains Mono via the same `@fontsource` npm packages `ui-src` uses (not Google Fonts CDN, now that there's a real build step). Verified in a real browser via Chrome DevTools MCP, not just visually eyeballed from the CSS.

**Why React specifically, not vanilla JS like `cartographer ui`:** explicitly requested. `cartographer ui` itself is vanilla JS + Vite, not React -- if you're looking for a vanilla-JS precedent to extend instead, that's where it lives, but this app intentionally diverges from it.

## Real AWS resources (created 2026-10-05, account `983883745126`, `us-east-1`)

| Resource | Value |
|---|---|
| S3 registry bucket (SR.1) | `cartographer-standards-registry-983883745126` |
| Cognito User Pool | `us-east-1_4TI3BpY8r` |
| Cognito App Client | `14dd9c9dfdso03eb301hls96b0` |
| Cognito Hosted UI domain | `cartographer-standards-11439652` |
| Postgres `registry_tokens` table | `cartographer_webapp` database, same Postgres instance as the central VDB backend (locally: `cli/tests/docker-compose.yml`'s `ci-pgvector-1` container, port 5433) |

Cognito groups `Author`/`Reviewer`/`Admin` exist with one test user each (`test-author@example.com`, `test-reviewer@example.com`, `test-admin@example.com`, password `TestPass123`) -- seeded by hand per SR.2's documented bootstrap pattern; replace with real users and/or SR.4's admin UI when that exists. One registry token is seeded in Postgres for `project_id = proj_test`; see whoever ran the SR.2 build for its value, or issue a new one directly:

```python
import secrets, hashlib
token = "sr2-" + secrets.token_urlsafe(32)
print("token:", token)
print("hash (put this in Postgres, not the token itself):", hashlib.sha256(token.encode()).hexdigest())
```

```bash
docker exec ci-pgvector-1 psql -U cartographer -d cartographer_webapp -c "
INSERT INTO registry_tokens (token_hash, project_id) VALUES ('<hash from above>', 'your-project-id');
"
```

Pack content itself (standards/skills/agents for all 12 bundled packs plus a 13th `"core"` entry for the cross-cutting skills/agents shared by every stack) is already published in the S3 bucket above -- see `scripts/publish_pack.py` if you need to republish or add a new pack.

## Running locally

**Prerequisite: the Postgres container.** The backend needs `DATABASE_URL` reachable (default in `.env.local` points at `localhost:5433`). Start it via `cli/tests/docker-compose.yml` if it isn't already running (`docker compose -f cli/tests/docker-compose.yml up -d pgvector`), and create the `cartographer_webapp` database + `registry_tokens` table once if they don't exist yet:

```bash
docker exec ci-pgvector-1 psql -U cartographer -d postgres -c "CREATE DATABASE cartographer_webapp;"
docker exec ci-pgvector-1 psql -U cartographer -d cartographer_webapp -c "
CREATE TABLE registry_tokens (
    token_hash TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);"
```

**Quick (backend only, serving the already-built frontend):**

```bash
cd webapp/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a; source .env.local; set +a   # gitignored -- ask whoever ran the SR.2 build for a copy, or recreate from the table above + Cognito client secret
.venv/bin/uvicorn app.main:app --reload
```

Open `http://localhost:8000` and log in as one of the seeded test users.

**While editing the frontend** (hot reload, run both at once):

```bash
# terminal 1
cd webapp/backend && set -a && source .env.local && set +a && .venv/bin/uvicorn app.main:app --reload

# terminal 2
cd webapp/frontend && npm install && npm run dev   # opens on :5173, proxies /api,/login,/auth,/logout to :8000
```

After any `frontend/src/` change meant to ship, rebuild and commit the output: `cd webapp/frontend && npm run build` (writes into `backend/app/static/dist/`, which is tracked in git -- commit it alongside the source change, same as `cli/ui-src`'s workflow).

## Running tests

```bash
cd webapp/backend
.venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/python -m pytest tests/ -v
```

These mock boto3/psycopg2 -- no AWS access or running Postgres needed. There's no frontend test suite yet (no test runner configured in `frontend/package.json`) -- the React app has been verified by hand via Chrome DevTools MCP (network-request inspection confirming SPA-only navigation, full click-through of every view). The real end-to-end proof (real Cognito token verification, real S3 reads, real CLI fetch against a live server) was also done manually during the SR.2 build; see that session's record for the commands, or re-run them against `.env.local`.

## Deploying to the existing EKS cluster

**Not done yet** -- this environment only has access to Docker Desktop's local Kubernetes (`kubectl config current-context` → `docker-desktop`), not the org's real shared EKS cluster. The manifests in `k8s/` are ready to apply but need, in order:

1. Build the frontend and commit the output if you haven't already (`cd webapp/frontend && npm run build`), then build and push the backend image, which bundles the already-built `backend/app/static/dist/`: `docker build -t <your-registry>/standards-webapp:latest webapp/backend && docker push ...`
2. Create the real IRSA role (read access to the S3 bucket above -- Postgres access is network/password-based via DATABASE_URL, not IAM) and update `k8s/serviceaccount.yaml`'s `role-arn` annotation.
3. Update `k8s/configmap.yaml`'s `BASE_URL` and `k8s/ingress.yaml`'s `host` to the real hostname this will be served at, and add that same URL (`https://<host>/auth/callback`) as a Cognito app client callback URL. **Important:** `update-user-pool-client` replaces the entire OAuth config, it does not merge -- any call must include `--allowed-o-auth-flows`, `--allowed-o-auth-scopes`, `--allowed-o-auth-flows-user-pool-client`, `--supported-identity-providers`, `--callback-urls`, and `--logout-urls` together, every time, even if you're only changing one of them. Omitting any of these silently wipes it (this happened once during the SR.2 build and broke login with a `redirect_mismatch` error until caught).
4. Create the real Secret (see `k8s/secret.example.yaml` -- do not commit real values).
5. Update `k8s/deployment.yaml`'s `image` field to match step 1.
6. `kubectl apply -f webapp/k8s/` against the real cluster, in a dedicated namespace (already defined in `namespace.yaml`) so this doesn't collide with other tenants.

## What's proven vs. not

Proven for real against live AWS resources during the SR.2 build, including a full browser click-through (Chrome DevTools MCP) of: the Cognito hosted-UI login form → callback → session → React app load → navigating Standards/Skills/Agents sidebar views → pack detail (including skills' nested `<skill-name>/SKILL.md` rendering) → version history → direct deep-link navigation (e.g. pasting `/skills/python/versions` directly) → logout. Network-request inspection confirmed sidebar navigation only issues `fetch()` calls, never a document reload. Also proven: the content endpoint's 401 paths (missing/invalid/revoked token) and 200 path for all three content types, and a real `cartographer stack add`/`init --stack` run fetching standards+skills+agents (for both the requested stack and the shared `"core"` pack) through this server. Not proven: anything involving the actual shared EKS cluster (no access to it from here).
