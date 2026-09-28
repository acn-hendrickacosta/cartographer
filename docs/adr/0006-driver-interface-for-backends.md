# ADR-0006: Driver interface for all VDB and KG backends

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

Cartographer supports multiple VDB and KG backends: local embedded defaults (LanceDB, Kuzu) and central backends for multi-developer teams (pgvector, Qdrant, Neo4j, Neptune, and others). Without a deliberate abstraction, each new backend requires changes to the hooks, skills, CLI commands, and MCP servers. This compounds with every new backend added.

Additionally, the central backend choice was intentionally kept cloud-agnostic: teams should be able to run their central backend on AWS, another cloud provider, or self-hosted infrastructure without changing the application code.

---

## Decision

We will implement a driver interface for both the VDB and the KG. All application code interacts with these stores exclusively through the driver interface. Backend selection is a configuration choice; changing backends requires no code changes outside the driver layer.

---

## Options considered

### Option A: Direct backend calls throughout the codebase

Each hook, skill, and CLI command calls the backend library directly. Simpler to start.

Tradeoffs: adding a second backend requires modifying every call site. Testing requires a real backend of each type. The coupling makes the central topology upgrade path a code change rather than a config change, contradicting a stated project goal.

### Option B: Driver interface with registered implementations (chosen)

A Python abstract base class defines the contract for each store (VDB, KG). Concrete driver classes implement the contract for each backend. A driver registry maps the `vdb.driver` and `kg.driver` config values to the appropriate class. Application code depends only on the abstract interface.

Tradeoffs: more upfront structure. The interface must be designed carefully; a poorly designed interface forces awkward implementations in some drivers. The contracts documented in `docs/contracts/` serve as the interface specification.

### Option C: Adapter pattern at the MCP server layer only

Application code calls the MCP tools, which are served by a server that abstracts the backend.

Tradeoffs: this is actually the architecture Cartographer uses for runtime calls from hooks and skills. But the CLI (promote, seed, doctor) also needs direct driver access outside of a Claude Code session where MCP servers are not running. A pure MCP-only abstraction does not cover the CLI use case.

---

## Rationale

The driver interface is the right abstraction because it satisfies two requirements simultaneously: it makes the central topology upgrade a config change (not a code change), and it makes the system cloud-agnostic (any conforming backend can be used regardless of cloud provider or hosting model). The MCP servers and the CLI share the same driver implementations, so the abstraction covers both runtime and setup paths.

The driver contract is documented in `docs/contracts/vdb-tools.md` and `docs/contracts/kg-tools.md`. These documents serve as the specification that both application code and driver implementations must conform to.

---

## Consequences

**Positive:**
- Adding a new backend requires only a new driver class and a config key registration. No changes to hooks, skills, or CLI commands.
- Cloud-agnostic by design. AWS Aurora + pgvector, a self-hosted Qdrant, and a managed Neptune are all equally valid central backends.
- Testing is clean: tests can use the local drivers (LanceDB, Kuzu) without standing up external services.
- The local and central backends share the same interface, so the codebase has one set of call sites regardless of topology.

**Negative / risks:**
- The interface must remain stable. Adding a required method to the base class is a breaking change for all driver implementations. New methods must be added as optional with a default no-op, or require a major version bump.
- Some backends have capabilities that cannot be expressed through the common interface (e.g. advanced vector filtering in Qdrant). Those capabilities are unavailable to callers who go through the driver interface. This is an acceptable tradeoff for the use cases Cartographer targets.

---

## Links

- VDB driver contract: [contracts/vdb-tools.md](../contracts/vdb-tools.md)
- KG driver contract: [contracts/kg-tools.md](../contracts/kg-tools.md)
- Related: [ADR-0003](0003-lancedb-for-local-vdb.md), [ADR-0004](0004-kuzu-for-local-kg.md)
- Contributing a driver: [CONTRIBUTING.md: Adding a backend driver](../CONTRIBUTING.md)
