# Security baseline

- Validate and sanitize input at system boundaries: user input, external APIs, file
  uploads. Do not add defensive checks for internal calls that cannot receive
  attacker-controlled data.
- Never commit secrets, credentials, or API keys. Configuration that carries secrets
  belongs in a gitignored local override or the environment, never in a committed
  file. Validate at startup that required secrets are present and fail fast if they
  are not.
- Treat anything that builds a shell command, SQL query, or HTML fragment from
  untrusted input as a candidate for injection until proven otherwise. Use
  parameterized queries and established escaping, not string concatenation.
- Source code is confidential by default. Do not send it to a third-party API
  (including an embedding API) unless the team has explicitly opted in and accepted
  the egress.
- When you find a vulnerability while working on something else, fix it immediately
  if it is small, or flag it clearly if it is not, rather than leaving it for later
  silently.
- Store authentication tokens in `httpOnly` cookies with `Secure` and `SameSite=Strict`
  attributes. Never store tokens in `localStorage` — it is accessible to any script
  on the page and is a direct XSS extraction target.
- Protect state-changing endpoints with CSRF tokens. `SameSite=Strict` cookies
  provide a baseline; add explicit CSRF token validation for APIs consumed by
  non-browser clients.
- Set a Content Security Policy starting from the strictest policy that works, and
  loosen only with a documented reason. Defaulting to `'unsafe-inline'` or
  `'unsafe-eval'` neutralizes most CSP protection.
- Rate limiting on production APIs must use a shared store (Redis, a gateway, or the
  platform's native limiter), not per-process in-memory counters. In-memory counters
  reset on deploy, split across replicas, and fail open in multi-instance and
  serverless environments.
- Error responses sent to clients must not contain stack traces, SQL error messages,
  or internal system details. Log full error context server-side; return a generic,
  structured error to callers.
- Scan dependencies for known CVEs regularly. Commit lock files and use `ci`-style
  installs (reproducible from lock) in CI pipelines. Enable automated dependency
  update PRs.
