# Redis

## Data Structure Selection

| Use Case | Structure |
|---|---|
| Simple cache or counter | String |
| User session | Hash |
| Ranked leaderboard | Sorted Set |
| Unique visitor count (approximate) | HyperLogLog |
| Activity feed | List |
| Durable event queue with delivery guarantees | Stream |
| Rate limit window | String with `INCR` |

## Caching Patterns

- **Cache-aside (lazy loading)**: check the cache on read; on miss, fetch from the
  database and write to the cache with a TTL. Simple and correct for most use cases.
- **Write-through**: update the cache immediately on every write. Keeps cache consistent
  at the cost of additional write latency.
- **Cache invalidation**: tag related keys with a set so they can be invalidated
  together when the underlying data changes.
- Always set a TTL on every cached key. Keys without TTL accumulate indefinitely and
  cause memory pressure without bound.
- Cache stampede (thundering herd) occurs when many requests miss the same cold key
  simultaneously. Use a per-key lock or probabilistic early expiry to serialize the
  fetch.

## Key Naming

- Use a hierarchical naming scheme: `resource:id:field` or `namespace:resource:id`.
  Consistent naming makes it possible to scan by prefix and reason about memory usage.
- Use time-bound keys for rolling windows: `stats:pageviews:2024-01-01`.

## TTL Guidelines

| Data Type | Suggested TTL |
|---|---|
| User session | 24h |
| API response cache | 5–15 min |
| Rate limit window | Match window size |
| Short-lived auth tokens | 5–10 min |
| Reference / static data | 1h–1 week |

## Rate Limiting

- Fixed-window rate limiting: `INCR` the key and `EXPIRE` it for the window duration.
  Simple and atomic with a pipeline.
- Sliding-window rate limiting: use a sorted set with timestamps as scores. Remove
  expired members, count remaining, add the new request if under the limit. Implement
  as a Lua script for atomicity.

## Distributed Locks

- Acquire a lock with `SET key token NX PX ttl`. The `NX` ensures only one caller
  succeeds; the `PX` TTL ensures the lock is released even if the holder crashes.
- Release with a Lua script that compares the token before deleting — never `DEL`
  unconditionally, or a slow holder may release another caller's lock.
- For multi-node Redis clusters, use the Redlock algorithm (or an established library
  implementing it) rather than a single-node lock.

## Streams vs Pub/Sub

- Use Pub/Sub for fire-and-forget fan-out where missed messages are acceptable.
- Use Streams when you need delivery guarantees, consumer groups, message acknowledgment,
  or the ability to replay from a past position.

## Eviction Policies

- `allkeys-lru`: good default for general caching. Evicts the least recently used key
  when memory is full.
- `noeviction`: for queues and critical data where eviction would corrupt state.
- Set `maxmemory` and an explicit `maxmemory-policy` in every production configuration.

## Anti-Patterns

- Keys with no TTL accumulate indefinitely.
- `KEYS *` in production blocks the server (O(N)). Use `SCAN` with a cursor instead.
- Storing large blobs (>100KB) in Redis causes slow serialization and memory pressure.
  Store references and fetch from an object store.
- Using a single Redis instance for unrelated use cases (cache, session, queue, pubsub)
  without logical separation. Use separate databases or instances for isolation.
- Ignoring connection pool limits leads to connection exhaustion under load.
