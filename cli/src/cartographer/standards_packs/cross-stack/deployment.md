# Deployment

## Deployment Strategies

- **Rolling deployment**: replace instances gradually, old and new versions run
  simultaneously during rollout. Requires backward-compatible changes. Suitable for
  most routine deployments.
- **Blue-green deployment**: run two identical environments; switch traffic atomically
  when the new version is verified. Enables instant rollback by switching back to the
  old environment. Requires 2× infrastructure during the cutover window.
- **Canary deployment**: route a small percentage of traffic to the new version first,
  observe metrics, then gradually increase. Catches issues with real traffic before
  full rollout. Requires traffic splitting infrastructure.
- Rolling is a safe default. Use blue-green for zero-tolerance cutover or when you need
  an instant rollback path. Use canary for high-traffic services with risky changes.

## CI/CD Pipeline

- A standard pipeline stages: lint → type check → unit tests → integration tests on
  merge to a release branch; add image build → staging deploy → smoke tests → production
  deploy on merge to main.
- CI must pass before any merge. Green CI is a gate, not a nicety. Merging red is
  technical debt that degrades signal for everyone.
- Build images in CI and push to a registry tagged by commit SHA. Deploy by updating
  the image tag, not by rebuilding at deploy time. This ensures what was tested is what
  runs in production.
- Cache dependency installation layers in CI (e.g., using GitHub Actions cache or
  Docker layer cache) to keep build times short.

## Health Checks and Readiness

- Every deployable service must expose a `/health` endpoint. At minimum it returns
  `200 OK` when the process is alive. A deeper `/health/detailed` can check database
  and cache reachability, but keep it separate from the liveness probe to avoid restart
  loops caused by downstream outages.
- Liveness and readiness are different: liveness detects a hung process (restart the
  container), readiness detects temporary unavailability (remove from load balancer
  without restarting). Use both in Kubernetes; do not conflate them.

## Environment Configuration

- All environment-specific configuration comes from environment variables, never from
  committed files. This is the twelve-factor app principle: config in the environment,
  code in the repo.
- Validate required environment variables at startup and fail fast with a clear error
  message if any are missing. A service that starts silently without required
  configuration will fail in surprising ways later.
- Document every required and optional environment variable in the repository.

## Rollback

- A rollback plan is required before any production deployment. Know in advance how to
  revert: which previous image tag, whether database migrations need reversal, and
  whether any in-flight requests will be affected.
- Design database migrations to be backward-compatible across at least one release
  cycle. If the old version of the code cannot run against the new schema, rolling
  rollback is not possible.
- Test the rollback path in staging. A rollback procedure that has never been practiced
  will fail under pressure.
- Feature flags allow new functionality to be disabled without a deploy. They decouple
  release from deployment and are one of the most effective rollback mechanisms for
  application-level changes.

## Production Readiness Checklist

- All tests pass (unit, integration, E2E) and CI is green.
- No hardcoded secrets in code or configuration files.
- Health check endpoint returns meaningful status.
- Environment variables documented and validated at startup.
- Structured (JSON) logging that does not contain PII or secrets.
- Resource limits set (CPU, memory) and horizontal scaling configured.
- SSL/TLS enabled on all public endpoints.
- Application metrics exported (request rate, latency, error rate).
- Alerts configured for error rate thresholds.
- Log aggregation set up and logs are searchable.
- Rollback plan documented and tested in staging.
- Database migrations tested against production-sized data.
- Runbook for common failure scenarios exists.
