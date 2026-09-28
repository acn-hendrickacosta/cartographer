# ADR-0003: LanceDB for the local vector database

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

The local VDB must run with no external service, no running process beyond the CLI itself, and no cloud account. It must persist on disk across sessions, support approximate nearest-neighbor search over embeddings, and be operable from Python. The brief listed LanceDB and Qdrant embedded as candidates.

---

## Decision

We will use LanceDB as the local embedded VDB. It is the default driver for `vdb.driver = "lancedb"` in `cartographer.toml`.

---

## Options considered

### Option A: Qdrant embedded

Qdrant offers an embedded mode that runs in-process. Strong filtering capabilities, mature Python client.

Tradeoffs: the embedded mode is a secondary concern for the Qdrant project, which is primarily a server product. Documentation and support for embedded mode lags the server. The embedded store format is not optimized for on-disk persistence in the way LanceDB is.

### Option B: LanceDB (chosen)

LanceDB is designed from the ground up as an embedded, on-disk vector store. The storage format (Lance columnar format) is optimized for persistence and fast reads without a running service. Zero dependencies beyond the Python package. First-class Python API.

Tradeoffs: smaller community than Qdrant. Fewer filtering options than a full server product. Acceptable for the local use case where filter complexity is low.

### Option C: pgvector with local Postgres

pgvector requires a running Postgres instance even for local use. Adds operational complexity that contradicts the no-service-required local default requirement.

---

## Rationale

LanceDB is purpose-built for the local embedded use case. It requires no running service, stores data on disk in the project directory, and restarts cleanly without any initialization ceremony. The on-disk format survives process restarts. This matches the Cartographer requirement exactly: the index must persist between Claude Code sessions without a developer having to start a service.

The driver interface means LanceDB is not a permanent commitment. A team that needs more filtering power or wants to run a local Qdrant server can swap the driver with a config change.

---

## Consequences

**Positive:**
- Zero-service local setup. `cartographer init` provisions the index with no external dependencies.
- Fast cold start: LanceDB opens an existing on-disk store in milliseconds.
- Storage format is portable: the `.cartographer/vdb/` directory can be copied or backed up as a plain directory.

**Negative / risks:**
- LanceDB embedded does not support concurrent writes from multiple processes. The ingest pipeline serializes writes; this is acceptable for the single-developer local use case.
- If LanceDB's Python API changes significantly, the driver must be updated.

---

## Links

- Related: [ADR-0006](0006-driver-interface-for-backends.md)
- VDB tool contracts: [contracts/vdb-tools.md](../contracts/vdb-tools.md)
- Configuration: [CONFIGURATION.md](../CONFIGURATION.md)
