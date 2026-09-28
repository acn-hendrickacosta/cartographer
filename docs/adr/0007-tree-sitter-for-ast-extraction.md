# ADR-0007: Use tree-sitter for language-agnostic AST extraction

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-09-28 |
| Deciders | Hendrick |

---

## Context

The KG ingestion pipeline currently extracts structural edges (symbol definitions, imports) using hand-written regex patterns per language. This approach has two concrete problems:

1. **It missed actual call sites.** In testing on the Disney styleguide-processing workspace, `kg_query` correctly surfaced five spec files that document behavior riding on `_build_prompt`, but missed the actual production call site at `area_validator.py:918`. Regex patterns match surface syntax; they cannot model the relationship between a function definition and its call sites.

2. **It does not scale across stacks.** Cartographer targets multi-stack repos (Python, TypeScript, Go, etc.). Maintaining per-language regex patterns for symbols, imports, and calls is fragile and does not generalize. A new language requires new patterns, each with its own edge cases.

The fix requires a real parse tree, not text matching.

---

## Decision

We will introduce a language-agnostic parser abstraction (`cli/src/cartographer/ingestion/parsers/`) backed by tree-sitter for all supported languages, with Python's stdlib `ast` module as the Python-specific implementation (no extra dependency). The abstraction defines a single `ParseResult` that all parsers return; `graph_extractor.py` consumes only `ParseResult` and is unaware of which parser produced it.

---

## Options considered

### Option A: Extend the existing regex approach

Add more regex patterns per language for call detection and class hierarchy.

Tradeoffs: no new dependencies, already partially in place. But regex cannot reliably detect call sites inside nested scopes, cannot distinguish a call from a string that looks like one, and cannot model attribute chains. Each language requires separate pattern maintenance with no shared abstraction.

### Option B: Python `ast` module only

Use Python's stdlib `ast` for Python files and leave other languages on regex.

Tradeoffs: zero extra dependencies, correct for Python. Does not address the multi-stack generalization problem. Makes the architecture asymmetric: Python gets a real parse tree, everything else gets regex. Any future JS/TS support requires a separate decision.

### Option C: tree-sitter with per-language grammars (chosen)

Use the `tree-sitter` Python bindings with installable grammar packages (`tree-sitter-python`, `tree-sitter-typescript`, `tree-sitter-go`, etc.). Define a `Parser` protocol and a registry that maps file extensions to parser instances. Python uses stdlib `ast` directly (not tree-sitter) to avoid a redundant dependency for the most common case.

Tradeoffs: adds `tree-sitter` as an optional dependency per supported language. Grammar packages must be installed separately (as pip extras). If a grammar is not installed, the registry falls back to the existing regex parser for that extension — no hard failure.

### Option D: Language Server Protocol / LSP

Delegate to running language servers (pylsp, ts-language-server, gopls, etc.) for call graph extraction.

Tradeoffs: accurate, handles cross-package resolution. But requires spawning and managing long-running processes per language, complex lifecycle management, and significant startup latency. Not appropriate for a CLI tool that runs in a CI or pre-commit context.

---

## Rationale

Option C is the only option that solves both problems: it handles call sites correctly (real parse tree) and generalizes across stacks (one abstraction, grammars registered per extension). The fallback to regex when a grammar is not installed means the tool degrades gracefully rather than failing hard, which is important for a CLI with optional dependencies.

Python uses stdlib `ast` rather than `tree-sitter-python` because `ast` is always available, battle-tested, and produces a richer typed AST than tree-sitter's generic node representation for this specific use case.

---

## Consequences

**Positive:**
- `calls` edges from actual call sites enter the KG. "What calls `_build_prompt`?" returns correct results.
- Adding a new language is one new file + one grammar pip extra + one registry entry in `parsers/__init__.py`.
- `graph_extractor.py` becomes simpler: one `parsers.parse(path, text)` call replaces three separate regex extraction functions.
- `cartographer doctor` can report which parsers (and therefore which languages) are active.

**Negative / risks:**
- `tree-sitter` grammar packages are maintained by the community. A grammar may lag behind a language spec release or have bugs for edge-case syntax. The regex fallback mitigates this — broken grammar = downgrade, not crash.
- tree-sitter grammars do not perform import resolution. A call to `_build_prompt` emits an edge to the symbol name; resolving which file defines that symbol requires a second pass (see Open Questions below).
- Binary size of grammar packages adds to the pipx venv. Each grammar is roughly 1–5 MB.

---

## Open questions

**Import resolution for cross-file calls**: tree-sitter gives us the call site (`area_validator.py` calls `_build_prompt`) but not which file defines `_build_prompt`. Two options:
1. Emit an unresolved stub node `symbol://_build_prompt` and let the KG query match it against defined symbol nodes by name.
2. Run a resolution pass after all files are ingested: for each unresolved call edge, look up the symbol name in the KG and rewrite the edge to point to the defining file's node.

Option 2 is more accurate but requires a post-ingestion pass. Defer this decision to implementation. Start with option 1 (stubs) and measure whether query quality is sufficient.

---

## Links

- Component spec: [ast-parser.md](../components/ast-parser.md)
- Related ADRs: ADR-0004 (KuZu for local KG), ADR-0006 (driver interface pattern)
- Feedback that motivated this: `area_validator.py:918` missed by KG but caught by grep — see project memory `feedback_kg_vs_grep.md`

---

*ADRs are append-only. To supersede this decision, create a new ADR and update the Status field here to "Superseded by ADR-XXXX".*
