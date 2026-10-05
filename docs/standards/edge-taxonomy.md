# Edge Type Taxonomy

Canonical, versioned list of edge types `RelatesTo` (local Kuzu) / `RELATES_TO`
(central Neo4j) relationships may carry in their `type` property. Governance
mechanism for Phase 4 (`docs/phases/phase-4-enterprise.md`, "Edge taxonomy
governance").

**Current version: 1.0** — matches `cartographer.taxonomy.CANONICAL_TAXONOMY_VERSION`,
the single source of truth the CLI checks against. This document is kept in
sync by hand; if you change the Python constant, update this table and bump
the version in the same change.

There is no remote taxonomy server in this project — "version" here means
the version bundled with the installed CLI, checked at `cartographer seed`
(lint step) and `cartographer doctor` (pin check), not a network call.

| Edge type | Source | Definition |
|---|---|---|
| `defines` | AST | File or module defines this symbol |
| `calls` | AST | Function or method calls another |
| `imports` | AST | File imports a module |
| `extends` | AST | Class extends or implements another |
| `implements_spec` | doc/code reference | Code or doc references a spec by id or pattern |
| `depends_on` | LLM enricher | Semantic dependency; only present with `--enrich` |
| `relates_to` | generic | Catch-all relationship not covered by a more specific type |
| `supersedes` | promote | New artifact supersedes a renamed-away old one (Phase 3.3 rename tracking) |

## Adding a new edge type

New types require:
1. A PR to this file adding the row (type, source, definition).
2. Adding the same type to `CANONICAL_EDGE_TYPES` in `cli/src/cartographer/taxonomy.py`.
3. A version bump (`CANONICAL_TAXONOMY_VERSION` here and in the Python constant) if the change is not purely additive-and-backward-compatible.

## Enforcement

- **`cartographer seed`**: after graph extraction, each file's emitted edge
  types are checked against this taxonomy. An edge type not in the list is
  dropped (not written) and reported as a warning by default. Pass `--strict`
  to fail the file instead.
- **`cartographer doctor`**: reports if the project's pinned `[taxonomy]
  version` doesn't match the installed CLI's version, and separately scans
  the local KG's actual edge types for any outside the canonical set
  (drift that predates the current pin, or came from a different CLI version).
- **`cartographer taxonomy list`**: prints this table from the CLI's own
  bundled copy, for a quick check without opening this file.
