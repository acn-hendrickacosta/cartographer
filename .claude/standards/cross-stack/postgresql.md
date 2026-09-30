# PostgreSQL

## Index Selection

| Query Pattern | Index Type |
|---|---|
| `WHERE col = value` or range | B-tree (default) |
| `WHERE a = x AND b > y` | Composite B-tree: equality columns first, then range |
| `WHERE jsonb @> '{}'` or full-text | GIN |
| Time-series ranges on large append-only tables | BRIN |

- Put equality columns before range columns in composite indexes.
- Use covering indexes (`INCLUDE`) when the query selects a small set of columns
  alongside the indexed key, to avoid table heap lookups.
- Use partial indexes (`WHERE deleted_at IS NULL`) to keep indexes small and fast when
  only a subset of rows is ever queried.
- Create indexes with `CONCURRENTLY` on production tables to avoid blocking writes.
  `CONCURRENTLY` cannot run inside a transaction block.

## Data Types

| Use Case | Correct Type | Avoid |
|---|---|---|
| IDs | `bigint` or `uuid` | `int`, random UUID for high-insert tables |
| Strings | `text` | `varchar(255)` (no benefit over `text` in Postgres) |
| Timestamps | `timestamptz` | `timestamp` (loses timezone info) |
| Money / exact decimal | `numeric(precision, scale)` | `float` / `double` (rounds) |
| Booleans | `boolean` | `varchar`, `int` |

## Common Patterns

- **UPSERT**: use `INSERT ... ON CONFLICT DO UPDATE` rather than a separate SELECT
  before INSERT.
- **Queue processing**: select the next job with `FOR UPDATE SKIP LOCKED` to allow
  concurrent workers without contention.
- **Cursor pagination**: `WHERE id > $last_id ORDER BY id LIMIT n` is O(1);
  `OFFSET n` is O(n) and degrades at high offsets.
- **Row Level Security**: wrap the auth function call in a subselect (`(SELECT auth.uid())`)
  to prevent re-evaluation per row. Enable RLS on all user-data tables and write
  explicit policies — the default (deny all) is safe but must be intentional.

## Configuration Baselines

- Set `idle_in_transaction_session_timeout` and `statement_timeout` to prevent
  runaway queries from holding locks indefinitely.
- Enable `pg_stat_statements` for query performance monitoring.
- Revoke public schema access (`REVOKE ALL ON SCHEMA public FROM public`) and grant
  only to the application role.

## Performance Diagnostics

- Identify slow queries with `pg_stat_statements`: sort by `mean_exec_time DESC` and
  filter for queries over a meaningful threshold (e.g., 100ms).
- Check for unindexed foreign keys — they cause sequential scans on joins.
- Monitor table bloat (`n_dead_tup`) and `last_vacuum` to ensure autovacuum is keeping
  up with delete/update workload.
