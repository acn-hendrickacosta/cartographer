# Containerization

## Dockerfile Best Practices

- Use multi-stage builds. A `deps` stage installs dependencies, a `build` stage
  compiles, and a `production` stage copies only the runtime artifacts. The production
  image contains no build tools, dev dependencies, or source files it does not need.
- Pin to specific image tags, not `:latest`. Use `node:22-alpine` or
  `node:22.12-alpine3.20`, not `node:latest`. Unpinned tags make builds
  non-reproducible and hide breaking changes.
- Run containers as a non-root user. Create a dedicated user and group in the
  Dockerfile (`addgroup`/`adduser`) and set `USER` before the `CMD`. Running as root
  in production is a security vulnerability.
- Add a `HEALTHCHECK` instruction so the container runtime knows when the app is ready
  and can detect hangs. Use `wget -qO-` or `python -c "import urllib.request; ..."` for
  a lightweight health probe.
- Use `.dockerignore` to exclude `node_modules`, `.git`, `.env` files, test coverage,
  build outputs, and any file that should not end up in the image layer cache.
- Copy dependency manifests first (before source code) so Docker can cache the
  dependency installation layer. Copying the full source first busts the cache on every
  source change.

## Container Security

- Set `readOnlyRootFilesystem: true` in production containers. Mount `emptyDir` or
  `tmpfs` volumes for paths that the app must write to at runtime.
- Drop all Linux capabilities with `cap_drop: [ALL]` and add back only what is
  genuinely required (e.g., `NET_BIND_SERVICE` if binding to port 80).
- Set `no-new-privileges: true` to prevent privilege escalation via setuid binaries.
- Never bake secrets into image layers. Use environment variables, a secrets manager,
  or Docker secrets. Any value written to an image layer during build can be extracted
  from the image even if overwritten later.
- In Compose, bind-mount database ports to `127.0.0.1:5432:5432`, not `0.0.0.0`, in
  development environments. Omit the host port binding entirely in production — the
  database should be reachable only within the Docker network.

## Development vs Production

- Use Docker Compose `override` files for development-specific settings (debug port,
  live-reload volumes, log level). Keep the base `docker-compose.yml` production-clean.
- Use anonymous volumes to protect container-installed packages from being overwritten
  by bind-mount source code: `- /app/node_modules`.
- Add `healthcheck` conditions to `depends_on` so the application container does not
  start before the database is ready to accept connections.

## Networking

- Services in the same Compose network resolve by service name: the `app` container
  reaches the `db` container at `postgres://db:5432`. Avoid hardcoded IP addresses.
- Segment networks to limit blast radius: place the database on a backend-only network
  that the frontend service cannot reach directly.

## Anti-Patterns

- Running as root inside the container.
- Using `:latest` tags in any environment.
- Storing all services in one container ("the big blob"). One process per container.
- Putting secrets in `docker-compose.yml` or environment files committed to version
  control.
- Using Docker Compose for multi-container production workloads without an orchestrator.
  Compose is a local and CI tool; use Kubernetes, ECS, or Swarm for production.
- Storing data in containers without named volumes. Containers are ephemeral; data not
  in a volume is lost on restart.
