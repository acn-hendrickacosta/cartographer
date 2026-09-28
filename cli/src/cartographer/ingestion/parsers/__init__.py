"""Parser registry — maps file extensions to Parser instances.

Usage:
    from cartographer.ingestion import parsers
    result = parsers.parse(path, text, rel_path)

Built-in parsers (always active, no extra deps):
  .py  → PythonParser (stdlib ast)
  *    → RegexParser (fallback)

Optional parsers (tree-sitter grammars, installed via pip extras):
  .ts/.tsx → TypeScriptParser  (pip install cartographer[parsers-ts])
  .go      → GoParser          (pip install cartographer[parsers-go])
  .rs      → RustParser        (pip install cartographer[parsers-rust])
"""

from __future__ import annotations

from pathlib import Path

from cartographer.ingestion.parsers.base import ParseResult, Parser
from cartographer.ingestion.parsers.python_parser import PythonParser
from cartographer.ingestion.parsers.regex_parser import RegexParser

_REGISTRY: dict[str, Parser] = {}
_FALLBACK: Parser = RegexParser()


def _register(ext: str, parser: Parser) -> None:
    _REGISTRY[ext] = parser


# Python is always available — no extra deps needed.
_py = PythonParser()
_register(".py", _py)

# tree-sitter based parsers — each registers itself only if the grammar is installed.
def _try_register_ts() -> None:
    try:
        from cartographer.ingestion.parsers.typescript_parser import TypeScriptParser
        _ts = TypeScriptParser()
        _register(".ts", _ts)
        _register(".tsx", _ts)
    except ImportError:
        pass

def _try_register_go() -> None:
    try:
        from cartographer.ingestion.parsers.go_parser import GoParser
        _register(".go", GoParser())
    except ImportError:
        pass

def _try_register_rust() -> None:
    try:
        from cartographer.ingestion.parsers.rust_parser import RustParser
        _register(".rs", RustParser())
    except ImportError:
        pass

_try_register_ts()
_try_register_go()
_try_register_rust()


def parse(path: Path, text: str, rel_path: str) -> ParseResult:
    """Parse a source file and return language-agnostic structural facts."""
    parser = _REGISTRY.get(path.suffix.lower(), _FALLBACK)
    return parser.parse(text, path, rel_path)


def active_parsers() -> dict[str, str]:
    """Return a mapping of extension → parser class name. Used by doctor."""
    result = {ext: type(p).__name__ for ext, p in _REGISTRY.items()}
    result["*"] = type(_FALLBACK).__name__
    return result
