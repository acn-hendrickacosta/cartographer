# Production Readiness

- "CI is green" is not the same as "production-ready." CI verifies behavior in a
  controlled environment; production readiness also covers security, operations,
  observability, and failure recovery.
- Audit production readiness before launches, before high-stakes releases, and after
  major merges — not just when something breaks.

## Security and Auth

- Public routes, API routes, and admin routes must be clearly separated. Every
  sensitive route must enforce authentication and authorization server-side.
- Secrets must not appear in client bundles, log output, example files, or committed
  configuration.
- Rate limits, CSRF protection, CORS policy, and file upload validation must be
  present at every endpoint that needs them.

## Data Integrity

- Database migrations must run cleanly against a production data snapshot before being
  applied to production. Destructive migrations, backfills, and data imports must be
  staged safely.
- Webhook handlers and background job processors must be idempotent. Replay, duplicate
  delivery, and out-of-order delivery are normal in distributed systems — handlers that
  fail on duplicates will fail in production.
- Write operations that must succeed or fail together belong in transactions.

## Operations

- The app must start from a clean checkout using documented commands. If "just run it"
  does not work, the onboarding documentation is broken.
- Required environment variables must be named, documented, validated at startup, and
  fail fast with a clear error if missing.
- A health check endpoint must prove that critical dependencies (database, cache,
  external APIs) are reachable — not just that the process is alive.
- Deploy, rollback, and incident-escalation paths must be documented. A rollback
  procedure that has never been practiced will fail under pressure.
- Logs must be useful without leaking secrets or personal data. Structured logging
  enables search and aggregation; unstructured logs do not.

## User Experience

- Launch-critical paths must be covered on both desktop and mobile.
- Loading, empty, error, and permission-denied states must tell the user what happened
  and what they can do next. Blank screens and generic "Something went wrong" messages
  are not acceptable in critical flows.
- There must be a support or recovery path when a critical operation fails.

## Scoring Heuristic

Consider a release blocked (do not ship) if any of these are true:
authentication or authorization is missing on sensitive data; payment or
fulfillment webhooks are not idempotent; required migrations cannot be run
safely; secrets are exposed in client bundles, logs, or committed files; or
there is no rollback path for a high-impact release.

Consider a release risky (ship only to a small rollout or internal beta) if CI
is not green or the launch-critical user path was not tested end to end.
