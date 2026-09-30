# Project instructions

<!-- BEGIN CARTOGRAPHER -->
## Cartographer knowledge index

This project has a persistent knowledge index. **Always use the MCP tools below before
answering questions about the codebase** — do not rely on memory or file browsing alone.

### MCP tools

- **cartographer-vdb** — semantic vector search over all indexed files, specs, and docs.
  Call this at the start of every task to find relevant context.
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

### When to call them

- **Session start**: call `cartographer-vdb` with a broad query about the task at hand.
- **Before editing**: search for existing implementations, related specs, and dependencies.
- **When asked about the codebase**: always search before answering from memory.

Standards live under `.claude/standards/`. Re-index after major changes with `cartographer seed`.
Do not edit the content between these markers by hand.
<!-- END CARTOGRAPHER -->
