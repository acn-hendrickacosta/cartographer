# Backend Patterns

## API Structure

- Use resource-based URLs for REST APIs. List operations at `GET /api/resource`, single
  resource at `GET /api/resource/:id`. Filter, sort, and paginate via query parameters.
- Separate the repository layer (data access) from the service layer (business logic).
  Controllers or route handlers should delegate to services, not query the database
  directly.
- The repository layer provides a stable interface for data operations. Business logic
  depends on the repository interface, not on a specific database library.
- Middleware handles cross-cutting concerns: authentication, logging, rate limiting,
  request ID injection. Keep it composable and focused on one concern per middleware.

## Database Access

- Select only the columns you need. `SELECT *` transfers unnecessary data, skips index-
  only scans, and couples code to schema changes.
- Eliminate N+1 queries by batching. Fetch a set of IDs in one query, build a lookup
  map, and assign related records without additional per-row queries.
- Always use parameterized queries. Never interpolate user-controlled input into SQL
  strings.
- Wrap related writes in transactions. If two operations must succeed or fail together,
  they belong in a single transaction.
- Add limits to all queries that can return unbounded result sets. An unbounded query
  is a latency and memory risk.

## Caching

- Use the cache-aside pattern for read-heavy data: check the cache, on miss fetch from
  the database and populate the cache with a TTL. Write-through keeps the cache current
  immediately on writes.
- Always set a TTL on cached entries. Entries without TTL accumulate indefinitely.
  Choose TTLs based on acceptable staleness: API responses 5–15 minutes, sessions up to
  24 hours, reference data up to a week.
- Invalidate by key when a write changes data that is cached. Tag-based invalidation
  (a set of keys associated with a tag) allows bulk invalidation of related entries.
- Cache stampede (thundering herd on cold start) is a real failure mode. Use a per-key
  lock or probabilistic early expiry to prevent multiple concurrent fetches for the same
  cold key.
- Rate limiting state must use a shared cache or gateway, not per-process in-memory
  counters, on multi-instance services.

## Error Handling

- Use a centralized error handler to produce consistent API error responses. Individual
  route handlers should throw typed errors; the handler maps them to status codes and
  response shapes.
- Distinguish operational errors (expected, can be handled) from programmer errors
  (unexpected, should surface as 500 and be logged). Never swallow programmer errors.
- Retry transient failures (network timeouts, upstream `503`) with exponential backoff
  and jitter. Do not retry `4xx` responses.

## Background Jobs

- Offload long-running or non-critical work to a queue. Route handlers that block on
  slow operations degrade the entire API. Return a queued response immediately and
  process asynchronously.
- Background jobs must have a dead-letter path for failures. Fire-and-forget jobs that
  silently fail create invisible data problems.
- Idempotent job design allows safe retries. If a job can be re-run without side
  effects, failures are recoverable without manual intervention.

## Logging

- Use structured (JSON) logging. Structured logs are searchable, filterable, and
  parseable by log aggregation systems. Log at levels: `info` for normal operations,
  `warn` for unexpected-but-recoverable situations, `error` for failures.
- Always attach a request ID to logs so related log lines can be correlated. Inject the
  request ID at middleware level so all downstream logs inherit it automatically.
- Never log secrets, passwords, tokens, or personally identifiable information.
