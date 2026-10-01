# Project instructions

<!-- BEGIN CARTOGRAPHER -->
## Cartographer knowledge index

This project has a persistent knowledge index. **VDB and KG are your primary search tools for every codebase task — understanding, editing, reviewing, or planning.** Use them before opening any file.

### Mandatory protocol — follow this order on every task

1. **VDB first** — call `vdb_search` with a query about the concept, symbol, or feature you need. It returns the most relevant files and excerpts ranked by semantic relevance.
2. **KG next** — use `kg_query` to trace callers, importers, dependents, and spec relationships from the files VDB returned.
3. **Read only what they point to** — open files with `Read` only after VDB or KG has identified them as relevant. Never open a file speculatively.

**Hard rules — these override default behavior:**
- Never run `grep`, `find`, or `Glob` to locate files or understand codebase structure. Ask the VDB instead — it searches everything semantically.
- Never read a file that VDB or KG has not first confirmed is relevant to the task.
- Never read a whole directory or module to get oriented. Search first, read the specific files the search returns.
- Exception: pattern-specific scans that VDB cannot do (finding all empty catch blocks, hardcoded credential patterns, running a linter) are acceptable *after* VDB/KG have established scope.

### MCP tools

- **cartographer-vdb** — semantic vector search over all indexed files, specs, and docs.
  Use for: finding files related to a concept, understanding what a module does,
  locating specs or decisions relevant to your task.

- **cartographer-kg** — knowledge graph queries (Cypher) over artifact relationships.
  Use for: finding what implements a spec, what calls a function, what imports a module,
  what extends a class, and traversing relationships between components.

  Available edge types on `RelatesTo`:
  - `calls` — function A calls function B (AST-derived, high confidence)
  - `imports` — file A imports file B (AST-derived, high confidence)
  - `extends` — class A extends class B (AST-derived, high confidence)
  - `defines` — file defines a symbol
  - `implements_spec` — code or doc references a spec
  - `depends_on` — semantic dependency (LLM-inferred, only present with --enrich)

  Example queries:
  ```
  MATCH (a:Artifact)-[r:RelatesTo {type: 'calls'}]->(b:Artifact)
  WHERE b.attrs CONTAINS 'my_function' RETURN a.path LIMIT 20

  MATCH (a:Artifact)-[r:RelatesTo {type: 'extends'}]->(b:Artifact)
  WHERE b.attrs CONTAINS 'BaseClass' RETURN a.path LIMIT 10
  ```

Standards live under `.claude/standards/`. Re-index after major changes with `cartographer seed`.
Do not edit the content between these markers by hand.
<!-- END CARTOGRAPHER -->
