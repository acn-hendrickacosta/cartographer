# Kotlin Database (Exposed ORM)

- Configure HikariCP explicitly: `isAutoCommit = false`, `transactionIsolationLevel = TRANSACTION_READ_COMMITTED`, set `maximumPoolSize`, `connectionTimeout`, and `idleTimeout` appropriate for your workload. Do not rely on defaults.
- Run schema migrations with Flyway before starting the application. Call `Flyway.configure().dataSource(url, user, password).load().migrate()` in application startup. Never use `SchemaUtils.create()` in production — that's for tests only.
- Define tables using Exposed's `object` + `UUIDTable` (or `IdTable`) DSL. Use `UUIDTable` for auto-generated UUIDs as primary keys.

```kotlin
object UsersTable : UUIDTable("users") {
    val email = varchar("email", 255).uniqueIndex()
    val name = varchar("name", 100)
    val createdAt = timestamp("created_at")
}
```

- Wrap all database access in `newSuspendedTransaction(Dispatchers.IO) { ... }` for suspend functions, or `transaction { ... }` for blocking contexts. Never access the database outside a transaction.
- Escape LIKE pattern wildcards before interpolating user input: replace `%` with `\%` and `_` with `\_` and pass the escape character to the LIKE expression. Failing to do this turns user input into a wildcard query.
- Use `batchInsert` for inserting multiple rows. Inserting rows one at a time in a loop is orders of magnitude slower for bulk operations.
- Use `upsertOnConflict` (Exposed 0.41+) for insert-or-update semantics rather than a manual select-then-insert-or-update.
- Paginate queries with `.limit(pageSize, offset = page * pageSize)`. Never call `.toList()` on a table without a limit in production.
- For DAO style, define `Entity` classes with `referrersOn` for one-to-many relationships. Prefer DSL style for complex queries — DAO relationships trigger additional queries when accessed outside the transaction.
- Store JSONB columns with a custom column type using `kotlinx.serialization`. Define a `JsonbColumn(name, serializer)` helper so JSONB fields are typed and serialized consistently.
- Test with an H2 in-memory database using `H2Dialect` for fast unit tests. For integration tests that rely on PostgreSQL-specific features (JSONB, window functions, `ON CONFLICT`), use Testcontainers with a real Postgres image.
