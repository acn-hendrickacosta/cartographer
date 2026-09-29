# TypeScript Patterns

## API Response Envelope

- Wrap all API responses in a consistent envelope. This makes error handling uniform and lets consumers type-guard on `success` before accessing `data`.

```typescript
interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  meta?: {
    total: number
    page: number
    limit: number
  }
}
```

## Repository Pattern

- Abstract data access behind a typed interface. This lets service code stay agnostic to the underlying store, and makes tests easy to mock.

```typescript
interface Repository<T, CreateDto, UpdateDto, Filters = Record<string, unknown>> {
  findAll(filters?: Filters): Promise<T[]>
  findById(id: string): Promise<T | null>
  create(data: CreateDto): Promise<T>
  update(id: string, data: UpdateDto): Promise<T>
  delete(id: string): Promise<void>
}
```

## Service Layer

- Keep business logic in service classes, not in controllers or route handlers. Services receive their dependencies (repositories, external clients) via constructor injection so they can be tested in isolation.

```typescript
class UserService {
  constructor(private readonly userRepo: UserRepository) {}

  async getActiveUsers(): Promise<User[]> {
    return this.userRepo.findAll({ active: true })
  }
}
```

## Result Type for Expected Failures

- When a function can fail in expected ways (not bugs), return a discriminated union rather than throwing. Callers then handle both paths explicitly.

```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E }

function parseJson<T>(raw: string): Result<T> {
  try {
    return { ok: true, value: JSON.parse(raw) as T }
  } catch (e) {
    return { ok: false, error: e as Error }
  }
}
```

## Generic Constraints

- Use constraints to express what a generic actually requires rather than reaching for `any`. A function that only needs `id` does not need to accept `unknown`.

```typescript
function findById<T extends { id: string }>(items: T[], id: string): T | undefined {
  return items.find((item) => item.id === id)
}
```

## Async Patterns

- Prefer `Promise.all` for independent parallel operations over sequential `await` in a loop.
- Never use `array.forEach(async fn)` — it does not await the promises. Use `for...of` or `Promise.all(array.map(async fn))`.

```typescript
// Wrong: sequential when parallel is fine
for (const id of ids) {
  await processItem(id)
}

// Correct: parallel execution
await Promise.all(ids.map((id) => processItem(id)))
```

## Singleton Pattern for Clients

- Database clients, Redis instances, and other stateful clients should be instantiated once and shared. Multiple instances open redundant connections.

```typescript
// lib/db.ts
const globalForDb = globalThis as unknown as { db?: DbClient }
export const db = globalForDb.db ?? createDbClient()
if (process.env.NODE_ENV !== 'production') globalForDb.db = db
```
