# ADR-0005: fastembed for the local embedder

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-24 |
| Deciders | Hendrick |

---

## Context

Cartographer must embed code, specs, and documentation to populate the VDB. The embedder is the component that converts text chunks into vectors. The primary constraint is that source code must not leave the developer's machine by default: for client projects and regulated data, egress to an external embedding API is unacceptable without explicit team consent.

The brief listed fastembed and sentence-transformers as candidates for the local embedder.

---

## Decision

We will use fastembed as the default local embedder driver (`embedder.driver = "fastembed"`). An API embedder driver is available as an explicit opt-in for teams that accept egress.

---

## Options considered

### Option A: sentence-transformers

Mature library with a large model selection. Well-documented. Widely used in the Python ML community.

Tradeoffs: heavier dependency footprint (PyTorch). Slower cold start. Model download on first run can be large (hundreds of MB). Acceptable quality but more operational weight than needed for this use case.

### Option B: fastembed (chosen)

fastembed is a lightweight embedding library built on ONNX Runtime. No PyTorch dependency. Faster cold start. Models are smaller and download quickly. Quality is comparable to sentence-transformers for retrieval tasks. First-class Python API.

Tradeoffs: smaller model selection than sentence-transformers. The default model (`BAAI/bge-small-en-v1.5`, 384 dimensions) covers the retrieval use case well. Teams needing a specific model for a specialized domain may need to switch to sentence-transformers or the API driver.

### Option C: API embedder (e.g. OpenAI, Bedrock)

Higher quality embeddings for some use cases. No local compute required.

Tradeoffs: source code leaves the machine. Unacceptable as a default for client code. Available as an explicit opt-in driver for teams that accept egress after reviewing the security implications.

---

## Rationale

The no-egress default is a hard security requirement (see [SECURITY_AND_ISOLATION.md](../SECURITY_AND_ISOLATION.md)). fastembed satisfies it with lower operational overhead than sentence-transformers. The ONNX Runtime backend means it installs cleanly on the platforms developers use (macOS, Linux, Windows) without a GPU requirement. The default model produces embedding quality sufficient for the retrieval use cases Cartographer needs (code recall, spec lookup, doc search).

The API driver is provided as an opt-in for teams where embedding quality is critical and egress is approved. It is not the default and requires explicit configuration and a confirmed acknowledgment in the local override file.

---

## Consequences

**Positive:**
- No source code egress by default. Works immediately after `pip install`.
- Lightweight installation: no PyTorch, smaller models.
- Consistent embedding dimensions across machines (controlled by the model name in config).

**Negative / risks:**
- The default model (`BAAI/bge-small-en-v1.5`) is English-only and general-purpose. Projects with non-English content or highly specialized domains may see lower recall quality.
- If the team changes the embedding model after the index is populated, the existing vectors must be recomputed (dimensions may change). `cartographer doctor` detects this mismatch.

---

## Links

- Related: [ADR-0006](0006-driver-interface-for-backends.md)
- Security context: [SECURITY_AND_ISOLATION.md: Data egress](../SECURITY_AND_ISOLATION.md)
- Configuration: [CONFIGURATION.md](../CONFIGURATION.md)
