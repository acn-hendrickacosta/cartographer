# Error Handling

- Surface errors at the boundary where they occur. Do not bury them in a `catch` that
  silently discards the failure and returns a zero value or null.
- Every `catch` block must handle, re-throw, or log the error. Empty catch blocks and
  catch blocks that only comment "shouldn't happen" are not acceptable.
- Use typed errors over string messages. Define an error hierarchy with a `code` field:
  `NotFoundError`, `ValidationError`, `UnauthorizedError`. Callers can then switch on
  type or code rather than parsing message strings.
- For operations where failure is a normal outcome (parsing, external calls), consider
  a Result type — `{ ok: true, value: T } | { ok: false, error: E }` — rather than
  throwing. This forces callers to handle the failure branch explicitly.
- User-facing error messages and developer error context are different things. Show
  friendly, actionable text to users. Log the full error, stack trace, and context
  server-side where only engineers see it.
- API error responses must follow a consistent envelope so clients can handle errors
  generically: `{ "error": { "code": "...", "message": "..." } }`. Never leak stack
  traces or internal details in API responses.
- Errors are part of the API contract. Document every error code a client may receive.
  Undocumented error codes are surprises that break clients.
- Retry transient failures (network timeouts, `503` responses) with exponential backoff
  and jitter. Do not retry client errors (`4xx`) — they will not succeed on retry.
- Circuit breakers prevent cascading failures when an upstream dependency is degraded.
  Track failure rate and open the circuit after a threshold, letting the system recover
  before resuming calls.
- Async operations that run in the background must have an error path. Fire-and-forget
  jobs that swallow errors create invisible failures. Log or report to a dead-letter
  queue.
- UI components should be wrapped in error boundaries to catch rendering exceptions and
  display a fallback state instead of crashing the entire page.
- Map error codes to user-readable strings in one place. Keep that mapping separate from
  business logic so it can be updated without touching error-producing code.
