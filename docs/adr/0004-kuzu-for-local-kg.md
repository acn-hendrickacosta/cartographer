# ADR-0004: Kuzu for the local knowledge graph

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

The local KG must run with no external service, support real graph traversal queries (multi-hop neighborhood lookups, pattern matching), persist on disk across sessions, and be operable from Python. The brief listed Kuzu embedded and a SQLite-backed triple store as candidates.

---

## Decision

We will use Kuzu as the local embedded knowledge graph. It is the default driver for `kg.driver = "kuzu"` in `cartographer.toml`.

---

## Options considered

### Option A: SQLite-backed triple store

A triple store (subject, predicate, object) implemented on top of SQLite. No additional dependencies. Multi-hop traversal requires recursive CTEs or iterative queries, which are verbose and slow on large graphs.

Tradeoffs: widely understood, zero new dependencies. Graph traversal is awkward and slow. Pattern matching is not idiomatic. Acceptable for very shallow lookups (depth 1) but degrades at depth 2+, which Cartographer uses in recall.

### Option B: Kuzu (chosen)

Kuzu is an embedded property graph database designed for in-process use, similar in spirit to DuckDB. It supports the Cypher query language, multi-hop traversal natively, and stores data on disk with no running service. First-class Python API.

Tradeoffs: less widely known than Neo4j or SQLite. Newer project with a smaller community. The Cypher API is mature; the embedded mode is Kuzu's primary focus.

### Option C: Neo4j embedded

Neo4j offers an embedded mode but it is a Java library and requires the JVM. Adds a heavyweight runtime dependency incompatible with a zero-service Python CLI.

---

## Rationale

Kuzu fills the same role for the KG that LanceDB fills for the VDB: a purpose-built embedded store that runs in-process with no service. The recall hooks issue multi-hop neighborhood queries (`kg_neighbors` at depth 2) in every prompt turn. These queries are idiomatic and fast in a property graph with native Cypher support. Implementing the same queries in SQLite would require recursive CTEs that become brittle and slow as the graph grows.

The driver interface means Kuzu is replaceable. A team upgrading to central topology can switch to Neo4j or Neptune with a config change.

---

## Consequences

**Positive:**
- Zero-service local setup. Kuzu opens an on-disk store with no initialization.
- Native Cypher support makes neighborhood and pattern queries concise and maintainable in the driver implementation.
- On-disk store persists across sessions identically to LanceDB.

**Negative / risks:**
- Kuzu is a younger project. API stability is high for the core operations used here, but minor version upgrades should be tested.
- The Cypher dialect Kuzu supports may diverge slightly from Neo4j Cypher. Driver implementations for Neo4j and Kuzu must be tested independently.

---

## Links

- Related: [ADR-0006](0006-driver-interface-for-backends.md)
- KG tool contracts: [contracts/kg-tools.md](../contracts/kg-tools.md)
- Configuration: [CONFIGURATION.md](../CONFIGURATION.md)
