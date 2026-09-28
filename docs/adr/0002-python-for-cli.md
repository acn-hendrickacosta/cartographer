# ADR-0002: Python for the CLI

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

The CLI (`cartographer`) needs a language that supports the embedding and graph tooling used in the state layer, installs cleanly via a standard package manager, and is familiar enough for contributors to maintain without friction. The brief listed Python and Node as candidates.

---

## Decision

We will implement the CLI in Python 3.11 or later, distributed as a pip-installable package.

---

## Options considered

### Option A: Node.js

Familiar to frontend-focused contributors. Strong CLI tooling (`commander`, `inquirer`). npm distribution is well-understood.

Tradeoffs: the embedding and graph libraries that Cartographer depends on (LanceDB, Kuzu, fastembed) have their primary APIs in Python. Using Node would require either calling Python subprocesses, using secondary bindings of uncertain quality, or maintaining a separate Python layer for data operations. This splits the codebase without meaningful benefit.

### Option B: Python (chosen)

LanceDB, Kuzu, and fastembed all have first-class Python APIs. The data science and ML tooling ecosystem -- which the embedder driver will draw from -- is Python-native. pip distribution is standard and well-understood.

Tradeoffs: Python is not a natural choice for fast CLI startup. Cold start is acceptable for a setup and maintenance tool (init, doctor, promote) that is not run on every keystroke.

---

## Rationale

The deciding factor is the state layer dependencies. LanceDB, Kuzu, and fastembed are the confirmed local backend choices (see ADR-0003, ADR-0004, ADR-0005). All three have mature Python APIs and either thin or non-existent Node bindings. Keeping the CLI in the same language as the state layer eliminates a language boundary in the most performance-sensitive part of the system: the ingestion pipeline.

---

## Consequences

**Positive:**
- Single language across CLI, ingestion pipeline, and backend drivers.
- Full access to the Python embedding and graph ecosystem.
- pip installation is a single command.

**Negative / risks:**
- Slower CLI startup than a compiled binary. Acceptable given that CLI commands are run infrequently.
- Python version management (pyenv, venv) adds a setup step for developers not already using Python.

---

## Links

- Related: [ADR-0003](0003-lancedb-for-local-vdb.md), [ADR-0004](0004-kuzu-for-local-kg.md), [ADR-0005](0005-fastembed-for-local-embedder.md)
- CLI spec: [components/cli.md](../components/cli.md)
