"""Phase 4: canonical edge-type taxonomy — governance for cross-project KG queries.

At single-project scale, a typo'd or inconsistent edge type is a minor
nuisance. At org scale, schema drift across projects makes cross-project
Cypher (kg_impact, federated overlays) unreliable — a query filtering on
`type = 'imports'` silently misses edges a different project emitted as
`import` or `imported_by`.

See docs/standards/edge-taxonomy.md for full definitions, source (AST vs.
LLM enricher), and cardinality notes. This module is the single source of
truth the CLI checks against; the doc is kept in sync by hand, the same
convention already used for the bundled standards packs.

There is no remote taxonomy server in this project yet (the Standards
Registry and web app track is a separate, not-yet-started effort per
ROADMAP.md) — "the server's current version" in the Phase 4 planning doc
means this module's CANONICAL_TAXONOMY_VERSION, bundled with the installed
CLI, not a network call.
"""

from __future__ import annotations

CANONICAL_TAXONOMY_VERSION = "1.0"

CANONICAL_EDGE_TYPES = frozenset({
    "defines",
    "calls",
    "imports",
    "extends",
    "implements_spec",
    "depends_on",
    "relates_to",
    "supersedes",
})

EDGE_TYPE_DEFINITIONS: dict[str, tuple[str, str]] = {
    # edge_type: (source, definition)
    "defines": ("AST", "File or module defines this symbol"),
    "calls": ("AST", "Function or method calls another"),
    "imports": ("AST", "File imports a module"),
    "extends": ("AST", "Class extends or implements another"),
    "implements_spec": ("doc/code reference", "Code or doc references a spec by id or pattern"),
    "depends_on": ("LLM enricher", "Semantic dependency; only present with --enrich"),
    "relates_to": ("generic", "Catch-all relationship not covered by a more specific type"),
    "supersedes": ("promote", "New artifact supersedes a renamed-away old one (Phase 3.3)"),
}


def lint_edge_types(edge_types: set[str]) -> set[str]:
    """Return the subset of edge_types not in the canonical taxonomy."""
    return edge_types - CANONICAL_EDGE_TYPES
