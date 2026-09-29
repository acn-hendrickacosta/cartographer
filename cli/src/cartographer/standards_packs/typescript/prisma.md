# Prisma Patterns

## Schema Design

- Use `@default(cuid())` as the default ID strategy — URL-safe, sortable, no collision risk. Use `@default(uuid())` for interoperability with external systems. Avoid `autoincrement()` for public-facing IDs.
- Add `@@index` on every foreign key and every column used in `WHERE` or `ORDER BY`. `@unique` already creates an index — no additional `@@index` needed for those columns.
- Declare `deletedAt DateTime?` upfront when soft delete is a foreseeable requirement. Adding `NOT NULL` columns later requires a multi-step migration on a live table.
- `@updatedAt` is set by Prisma only on `update` and `upsert`. Bulk writes via `updateMany` do not trigger it — set `updatedAt: new Date()` explicitly in bulk operations.

```prisma
model User {
  id        String    @id @default(cuid())
  email     String    @unique
  name      String
  role      Role      @default(USER)
  createdAt DateTime  @default(now())
  updatedAt DateTime  @updatedAt
  deletedAt DateTime?

  @@index([createdAt])
  @@index([deletedAt, createdAt])
}
```

## Queries: `include` vs `select`

- Use `include` when you need most fields plus a relation. Use `select` on hot paths or wide tables to avoid over-fetching.
- Never return raw Prisma entities from API responses. Map to response DTOs to control exposed fields and avoid leaking internal columns (password hashes, tokens, audit fields).

```typescript
// Good: explicit DTO mapping
const raw = await prisma.user.findUniqueOrThrow({ where: { id } })
return { id: raw.id, name: raw.name, email: raw.email }
```

## Transactions

- Use the array form when operations are independent — it batches them in one round trip.
- Use the interactive form when a later step depends on an earlier result. Inside the callback, use only the `tx` client, never the outer `prisma` client.
- Keep transactions short. The interactive form times out after 5 seconds by default. Never make external calls (email, HTTP) inside a transaction.

```typescript
// Array form: independent operations
const [user, post] = await prisma.$transaction([
  prisma.user.update({ where: { id }, data: { name } }),
  prisma.post.create({ data: { title, authorId: id } }),
])

// Interactive form: dependent operations
const post = await prisma.$transaction(async (tx) => {
  const user = await tx.user.findUniqueOrThrow({ where: { id } })
  if (user.role !== 'ADMIN') throw new Error('Forbidden')
  return tx.post.create({ data: { title, authorId: user.id } })
})
```

## PrismaClient Singleton

- Instantiate `PrismaClient` once per process. Each instance opens its own connection pool. Use `globalThis` to prevent duplicate instances during hot reload.

```typescript
// lib/prisma.ts
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient }
export const prisma = globalForPrisma.prisma ?? new PrismaClient({
  log: process.env.NODE_ENV === 'development' ? ['query', 'error'] : ['error'],
})
if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma
```

## N+1 Prevention

- Loading relations inside a loop is an N+1 — one extra query per parent row. Use `include` or `select` with nested relations to load in a single query.

```typescript
// Wrong: N+1
const users = await prisma.user.findMany()
for (const user of users) {
  const posts = await prisma.post.findMany({ where: { authorId: user.id } })
}

// Correct: single query
const users = await prisma.user.findMany({ include: { posts: true } })
```

## Cursor Pagination

- Prefer cursor-based pagination over offset for feeds and large datasets. Fetch `limit + 1` rows to detect whether a next page exists, then pop the extra row. Always include a unique secondary sort field to prevent unstable results when timestamps collide.

```typescript
async function getPosts(cursor?: string, limit = 20) {
  const items = await prisma.post.findMany({
    where: { published: true },
    orderBy: [{ createdAt: 'desc' }, { id: 'desc' }],
    take: limit + 1,
    ...(cursor && { cursor: { id: cursor }, skip: 1 }),
  })
  const hasNextPage = items.length > limit
  if (hasNextPage) items.pop()
  return { items, nextCursor: hasNextPage ? items[items.length - 1].id : null }
}
```

## Error Handling

- Catch `Prisma.PrismaClientKnownRequestError` at the service boundary and translate to domain errors. Never expose raw Prisma messages to API consumers.

```typescript
import { Prisma } from '@prisma/client'

try {
  await prisma.user.create({ data: { email } })
} catch (e) {
  if (e instanceof Prisma.PrismaClientKnownRequestError) {
    if (e.code === 'P2002') throw new ConflictError('Email already exists')
    if (e.code === 'P2025') throw new NotFoundError('Record not found')
  }
  throw e
}
```

Common codes: `P2002` unique constraint violation · `P2025` record not found · `P2003` foreign key violation.

## Migrations

- Run `prisma migrate deploy` in CI/CD and all shared environments. Reserve `prisma migrate dev` for local development only — it detects schema drift and may prompt to reset the database.
- Never manually edit a migration file after it has been applied. Prisma checksums migration files; editing after deployment causes `P3006 checksum mismatch` on every other environment.
- For breaking schema changes (adding `NOT NULL` columns, renaming columns), use the expand-and-contract pattern: add the nullable column, backfill data in a script, then add the constraint in a separate migration.

## Soft Delete Gotcha

- `findUniqueOrThrow` does not filter by `deletedAt`. It returns soft-deleted rows without error.
- Use `findFirstOrThrow` with `where: { id, deletedAt: null }` — `findFirstOrThrow` supports arbitrary conditions, while `findUniqueOrThrow` only accepts unique constraint fields.

## Serverless Connection Pooling

- In serverless environments (Vercel, AWS Lambda), cap the connection pool to 1 per instance. Use an external connection pooler (PgBouncer, Supabase pooler) to prevent connection exhaustion across many concurrent invocations.
- Embed connection pool settings in the `DATABASE_URL` string: `?connection_limit=1&pool_timeout=20`.
