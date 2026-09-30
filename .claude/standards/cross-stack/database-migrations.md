# Database Migrations

- Every schema change is a migration. Never alter a production database manually;
  manual changes are unrepeatable, produce no audit trail, and will cause drift between
  environments.
- Migrations are forward-only in production. Roll back by writing a new forward
  migration, not by reverting the previous one. Reverting a migration that has run
  in production risks data loss and breaks the migration sequence for other environments.
- Schema changes and data migrations are separate. Mixing DDL and DML in a single
  migration creates long-running transactions, makes rollback complicated, and can lock
  tables longer than necessary.
- Migrations are immutable once deployed. Never edit a migration file that has run in
  any shared environment. Create a new migration instead.
- Test migrations against a copy of production data before applying them to production.
  A migration that completes in seconds on 100 rows may lock for minutes on 10 million.

## Safety Checklist

Before applying any migration, verify:
- New columns are nullable or have a default — adding `NOT NULL` without a default
  rewrites every row and locks the table.
- Indexes on large tables are created with `CONCURRENTLY` to avoid blocking writes.
- Data backfills are batched and use `SKIP LOCKED` or similar to avoid long lock
  contention.
- A rollback or recovery plan is documented.
- The migration has been reviewed for long-lock operations.

## Patterns for Zero-Downtime Changes

- **Adding a column**: add nullable or with a default first. Postgres 11+ applies
  `NOT NULL DEFAULT` instantly without a rewrite; earlier versions require a multi-step
  approach.
- **Adding an index without downtime**: use `CREATE INDEX CONCURRENTLY`. This cannot
  run inside a transaction block — most migration tools need explicit handling for this.
- **Renaming a column** (expand-contract): add the new column → backfill data in a
  separate migration → update application to write both columns → deploy → drop the
  old column. Never rename in a single step in production.
- **Removing a column**: remove all application references first, deploy, then drop the
  column in the next migration. Dropping a column before removing code causes
  application errors immediately.
- **Large data migrations**: batch updates in chunks (e.g., 10,000 rows at a time) with
  `COMMIT` between batches. Single-transaction updates on millions of rows hold locks
  for the full duration.

## Common Anti-Patterns

| Anti-Pattern | Why It Fails | Fix |
|---|---|---|
| Manual SQL in production | Unrepeatable, no audit trail | Always use migration files |
| Editing a deployed migration | Causes environment drift | Create a new migration |
| `NOT NULL` without a default on existing table | Table lock and full rewrite | Add nullable first, backfill, then add constraint |
| Inline index on large table | Blocks writes during build | `CREATE INDEX CONCURRENTLY` |
| Schema + data in one migration | Long transactions, hard rollback | Separate migrations |
| Dropping column before removing code | Application errors immediately | Remove code first, drop column next deploy |
