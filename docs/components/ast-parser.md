# Component: AST Parser Layer

**Status**: Specified, not yet implemented  
**Supersedes**: regex-based extraction in `graph_extractor.py` (`_extract_symbols`, `_extract_imports`, `_extract_python_calls`)  
**Decision**: [ADR-0007](../adr/0007-tree-sitter-for-ast-extraction.md)

---

## Purpose

Extract structural facts from source files — symbol definitions, call sites, imports, and class hierarchy — and return them in a language-agnostic `ParseResult`. The `graph_extractor` converts `ParseResult` into KG nodes and edges. Parsers know nothing about the KG; the graph extractor knows nothing about languages.

---

## Directory layout

```
cli/src/cartographer/ingestion/parsers/
  __init__.py        # registry: ext → Parser; parse() entry point
  base.py            # ParseResult, SymbolDef, CallEdge, ImportEdge, ExtendsEdge
  python_parser.py   # uses stdlib ast — no extra dep
  typescript_parser.py  # tree-sitter-typescript (optional)
  javascript_parser.py  # tree-sitter-javascript (optional)
  go_parser.py          # tree-sitter-go (optional)
  rust_parser.py        # tree-sitter-rust (optional)
  regex_parser.py    # current regex approach — fallback for unsupported langs
```

---

## Data model

### `base.py`

```python
from dataclasses import dataclass, field

@dataclass
class SymbolDef:
    name: str
    kind: str          # "function" | "method" | "class"
    line: int          # 1-indexed

@dataclass
class CallEdge:
    caller: str        # name of the containing function/method
    callee: str        # name of the function being called
    line: int

@dataclass
class ImportEdge:
    module: str        # dotted module path or file path (e.g. "cartographer.config")
    names: list[str]   # imported names (["load_config", "save_config"]); empty = wildcard/module import

@dataclass
class ExtendsEdge:
    child: str         # class name doing the inheriting
    parent: str        # base class name

@dataclass
class ParseResult:
    symbols:  list[SymbolDef]  = field(default_factory=list)
    calls:    list[CallEdge]   = field(default_factory=list)
    imports:  list[ImportEdge] = field(default_factory=list)
    extends:  list[ExtendsEdge]= field(default_factory=list)

class Parser:
    """Protocol — all parsers implement this."""
    def parse(self, text: str, path: Path) -> ParseResult: ...
```

---

## Registry (`__init__.py`)

```python
_REGISTRY: dict[str, Parser] = {}
_FALLBACK = RegexParser()

def register(ext: str, parser: Parser) -> None:
    _REGISTRY[ext] = parser

def parse(path: Path, text: str) -> ParseResult:
    parser = _REGISTRY.get(path.suffix.lower(), _FALLBACK)
    return parser.parse(text, path)
```

Parsers register themselves on import. Each optional parser guards its import with a try/except:

```python
# typescript_parser.py
try:
    import tree_sitter_typescript
    register(".ts", TypeScriptParser())
    register(".tsx", TypeScriptParser())
except ImportError:
    pass  # falls back to regex
```

Python parser registers unconditionally (stdlib only):

```python
# python_parser.py
register(".py", PythonParser())
```

---

## Python parser

Uses `ast.parse()`. No tree-sitter dependency.

**Symbols**: walk `FunctionDef`, `AsyncFunctionDef`, `ClassDef` at any nesting level. Record name, kind, and line number.

**Calls**: for each `FunctionDef`/`AsyncFunctionDef`, walk its subtree for `ast.Call` nodes. Emit a `CallEdge(caller=fn.name, callee=<resolved name>)`. Skip names in a builtin blocklist (see below).

**Imports**: walk `ImportFrom` and `Import` nodes. Emit `ImportEdge(module=..., names=[...])`.

**Extends**: walk `ClassDef`. For each base in `node.bases`, emit `ExtendsEdge(child=node.name, parent=<base name>)`. Only emit for `ast.Name` and `ast.Attribute` bases (skip computed bases).

**Callee resolution within the parser**: use the file's own import map to attempt cross-file resolution.
- If `callee_name` is in the import map → set `callee_module` to the resolved module path.
- If not → treat as a same-file call (callee lives in the current file or is unresolvable).
- The graph extractor handles the unresolvable case by emitting a stub node.

**Builtin blocklist** (calls to skip — too noisy, no KG value):
```python
BUILTINS = {
    "print", "len", "range", "type", "str", "int", "float", "bool",
    "list", "dict", "set", "tuple", "isinstance", "issubclass",
    "hasattr", "getattr", "setattr", "delattr", "callable",
    "iter", "next", "enumerate", "zip", "map", "filter",
    "sorted", "reversed", "any", "all", "sum", "min", "max",
    "abs", "round", "repr", "open", "super", "vars", "dir",
    "id", "hash", "input", "format", "chr", "ord", "hex", "oct", "bin",
    # common exceptions
    "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "NotImplementedError",
    # common methods (attribute calls on unknown objects)
    "append", "extend", "insert", "remove", "pop", "update",
    "get", "items", "keys", "values", "join", "split", "strip",
    "lower", "upper", "replace", "encode", "decode", "format",
}
```

---

## tree-sitter parsers (TypeScript, Go, Rust, …)

Each parser follows the same pattern:

```python
import tree_sitter_typescript as ts_lang
from tree_sitter import Language, Parser as TSParser

_LANG = Language(ts_lang.language())

class TypeScriptParser:
    def __init__(self):
        self._parser = TSParser(_LANG)

    def parse(self, text: str, path: Path) -> ParseResult:
        tree = self._parser.parse(text.encode())
        result = ParseResult()
        self._walk(tree.root_node, result, current_fn=None)
        return result

    def _walk(self, node, result, current_fn):
        if node.type == "function_declaration":
            name = _child_text(node, "name")
            result.symbols.append(SymbolDef(name=name, kind="function", line=node.start_point[0] + 1))
            for child in node.children:
                self._walk(child, result, current_fn=name)
        elif node.type == "call_expression" and current_fn:
            callee = _call_name(node)
            if callee and callee not in BUILTINS:
                result.calls.append(CallEdge(caller=current_fn, callee=callee, line=node.start_point[0] + 1))
        # ... class_declaration, import_statement, extends_clause
        else:
            for child in node.children:
                self._walk(child, result, current_fn)
```

The exact node type names vary by grammar — each parser is responsible for mapping its grammar's node types to `ParseResult`. The interface contract is fixed.

---

## Regex fallback parser

Wraps the current `_extract_symbols`, `_extract_imports`, and `_extract_spec_refs` logic from `graph_extractor.py` into the `Parser` protocol. Returns a `ParseResult` with `symbols` and `imports` populated; `calls` and `extends` are empty (regex cannot reliably detect these).

Used for any extension not covered by a registered parser.

---

## Integration with `graph_extractor.py`

Replace the three separate extraction functions with:

```python
from cartographer.ingestion import parsers

def extract(...) -> ExtractedGraph:
    ...
    if artifact_type == ArtifactType.CODE:
        parse_result = parsers.parse(path, text)
        _emit_from_parse_result(parse_result, rel_path, project_id, scope, file_node_id, nodes, edges, workspace_root)
    ...
```

`_emit_from_parse_result` converts each field of `ParseResult` into KG nodes and edges:

| ParseResult field | KG edge type | Notes |
|---|---|---|
| `symbols` | `defines` (file → symbol node) | symbol node: `type="symbol"`, attrs include kind + line |
| `calls` | `calls` (symbol → symbol node) | callee node may be a stub if cross-file and unresolved |
| `imports` | `imports` (file → file/module node) | module node: `type="module"`, path = module path |
| `extends` | `extends` (symbol → symbol node) | parent node may be a stub if defined in another file |

Stub nodes (for unresolved callees/parents) use `type="stub"` and `path="symbol://<name>"`. A future resolution pass can rewrite these edges once all files are ingested.

---

## `cartographer doctor` output

Add a parser section to doctor output:

```
parsers:
  .py    python (stdlib ast)          ✓ active
  .ts    typescript (tree-sitter)     ✓ active
  .tsx   typescript (tree-sitter)     ✓ active
  .go    go (tree-sitter)             ✗ not installed  (pip install cartographer[parsers-go])
  .rs    rust (tree-sitter)           ✗ not installed  (pip install cartographer[parsers-rust])
  *      regex fallback               ✓ active (all other extensions)
```

---

## `pyproject.toml` extras

```toml
[project.optional-dependencies]
parsers-ts  = ["tree-sitter>=0.23", "tree-sitter-typescript>=0.23"]
parsers-go  = ["tree-sitter>=0.23", "tree-sitter-go>=0.23"]
parsers-rust= ["tree-sitter>=0.23", "tree-sitter-rust>=0.23"]
parsers-all = [
    "tree-sitter>=0.23",
    "tree-sitter-typescript>=0.23",
    "tree-sitter-go>=0.23",
    "tree-sitter-rust>=0.23",
]
```

Python gets full AST extraction with no extras. Install `parsers-ts` for TypeScript/JS repos, `parsers-all` for mixed stacks.

---

## What this does NOT cover

- **Cross-file callee resolution**: a call to `_build_prompt` emits an edge to a stub. Resolving which file actually defines it requires a post-ingestion pass not specified here.
- **Cross-service edges**: REST endpoint → HTTP client call, SSE event name matching, message queue routing. These are string-matched contracts, not syntactic calls. Out of scope for this layer.
- **Spec↔code semantic links**: stay in the LLM enricher (`--enrich` flag). The parser layer is purely structural.
- **Dynamic dispatch**: calls through `getattr`, reflection, or dependency injection are invisible to a static parser.

---

## Implementation order

1. `base.py` — data model (no deps, testable immediately)
2. `regex_parser.py` — wrap existing logic, wire into registry (zero behavior change, migration step)
3. `python_parser.py` — stdlib `ast` implementation
4. Update `graph_extractor.py` to call `parsers.parse()` and emit from `ParseResult`
5. Re-seed Disney workspace, verify `calls` edges appear for `_build_prompt`
6. `typescript_parser.py` + extras (when a TS workspace needs it)
7. Additional grammars on demand
