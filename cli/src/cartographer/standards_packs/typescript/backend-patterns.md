# Node.js Backend Patterns

## RESTful API Design

- Use resource-based URLs with standard HTTP verbs. `GET /api/users` lists, `GET /api/users/:id` fetches one, `POST /api/users` creates, `PUT`/`PATCH` updates, `DELETE` removes.
- Use query parameters for filtering, sorting, and pagination: `GET /api/users?status=active&sort=name&limit=20&offset=0`.
- Return a consistent response envelope so every consumer handles the same shape. Include `success`, `data`, and `error` fields.

## Repository and Service Layers

- Keep data access logic behind a typed repository interface. Controllers and route handlers call the service; the service calls the repository. This separation makes each layer independently testable.
- Business logic belongs in services, not in controllers. A controller parses the HTTP request, calls a service method, and serializes the response — nothing more.

```typescript
class UserService {
  constructor(private readonly userRepo: UserRepository) {}

  async getActiveUsers(): Promise<User[]> {
    return this.userRepo.findAll({ active: true })
  }
}
```

## Middleware for Cross-Cutting Concerns

- Auth, logging, rate limiting, and request correlation belong in middleware, not scattered across handlers.
- Use a higher-order function pattern so handlers receive typed, already-validated context.

```typescript
export function withAuth(handler: AuthenticatedHandler): Handler {
  return async (req, res) => {
    const token = req.headers.authorization?.replace('Bearer ', '')
    if (!token) return res.status(401).json({ error: 'Unauthorized' })
    try {
      req.user = await verifyToken(token)
      return handler(req, res)
    } catch {
      return res.status(401).json({ error: 'Invalid token' })
    }
  }
}
```

## Database Query Hygiene

- Select only the columns you need, not `SELECT *`. Wide rows over many requests add latency and memory pressure.
- Avoid N+1 queries — fetching related records in a loop issues one query per row. Batch load related records in a single query, then join in memory.

```typescript
// Wrong: N+1
for (const order of orders) {
  order.user = await getUser(order.userId)
}

// Correct: batch fetch
const userIds = orders.map((o) => o.userId)
const users = await getUsers(userIds)
const userMap = new Map(users.map((u) => [u.id, u]))
orders.forEach((o) => { o.user = userMap.get(o.userId) })
```

## Error Handling

- Define a typed `ApiError` class and a centralized error handler. Translate known error types (validation, not found, unauthorized) to appropriate HTTP status codes. Log unexpected errors and respond with a generic message — do not leak stack traces or internal details.
- Catch errors at the route level, not inside every helper, so the handler always returns a response.

```typescript
class ApiError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message)
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

function handleError(error: unknown): Response {
  if (error instanceof ApiError) {
    return Response.json({ success: false, error: error.message }, { status: error.statusCode })
  }
  if (error instanceof z.ZodError) {
    return Response.json({ success: false, error: 'Validation failed', details: error.issues }, { status: 400 })
  }
  console.error('Unexpected error:', error)
  return Response.json({ success: false, error: 'Internal server error' }, { status: 500 })
}
```

## Retry with Exponential Backoff

- Transient failures (network timeouts, rate limits) should be retried with exponential backoff and a cap. Do not retry unconditionally — check whether the failure is retryable first.

```typescript
async function withRetry<T>(fn: () => Promise<T>, maxRetries = 3): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn()
    } catch (error) {
      if (i === maxRetries - 1) throw error
      await new Promise((r) => setTimeout(r, Math.pow(2, i) * 1000))
    }
  }
  throw new Error('unreachable')
}
```

## Caching

- Cache expensive or frequently repeated lookups with a shared store (Redis, Memcached). Do not use per-process in-memory Maps for production caches — they reset on deploy, are not shared across replicas, and grow unbounded.
- Use a cache-aside pattern: check the cache first; on miss, fetch from the source and populate the cache with a TTL.

## Rate Limiting

- Rate limiting must use a shared store or gateway. Per-process in-memory counters reset on deploy, are not shared across instances, and fail open in serverless environments.

## Structured Logging

- Use a structured logger that emits JSON. Include a request ID (generated per request, propagated via context) in every log line so correlated logs can be found across services.
- Log at the appropriate level: `info` for normal operations, `warn` for recoverable anomalies, `error` for unexpected failures. Never log secrets, tokens, or PII.

## Authentication and Authorization

- Verify JWT tokens server-side on every protected request. Do not trust client-supplied user IDs or roles — derive them from the verified token.
- Implement role-based access control via permission checks in the service layer, not just at the route level.

```typescript
const rolePermissions: Record<UserRole, Permission[]> = {
  admin: ['read', 'write', 'delete'],
  user: ['read'],
}

function requirePermission(user: User, permission: Permission): void {
  if (!rolePermissions[user.role].includes(permission)) {
    throw new ApiError(403, 'Insufficient permissions')
  }
}
```

## Synchronous Operations in Event Loop

- Never use synchronous file I/O (`fs.readFileSync`, `fs.writeFileSync`) inside a request handler. Synchronous calls block the Node.js event loop for every concurrent request. Use the async variants with `await`.
