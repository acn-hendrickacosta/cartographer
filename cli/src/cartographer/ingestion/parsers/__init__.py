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

import sys
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


# Which standards-pack stack expects which tree-sitter grammar for full AST
# parsing (calls/extends edges), keyed by stack name from commands/stack.py's
# KNOWN_PACKS. Used by `stack add` and `doctor` to nudge installing the right
# extra instead of silently falling back to regex forever.
#
# The package list is duplicated from pyproject.toml's [project.optional-dependencies]
# rather than read via importlib.metadata: editable installs (`pip install -e .`) bake
# their dependency metadata in at install time and don't refresh it when pyproject.toml
# is edited afterward, so metadata.metadata("cartographer") can silently go stale.
# Keep this in sync with pyproject.toml by hand — it's a short, rarely-changing list.
STACK_PARSER_HINTS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    # stack name -> (import module to probe, pip extra, file types, pip package specs)
    "react": (
        "tree_sitter_typescript",
        "parsers-ts",
        ".ts/.tsx",
        ("tree-sitter>=0.23", "tree-sitter-typescript>=0.23"),
    ),
}


def is_parser_installed(import_name: str) -> bool:
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False


def _is_pipx_managed() -> bool:
    """pipx-managed venvs have no `pip` binary — `pip install` fails outright
    there (confirmed: `ModuleNotFoundError: No module named pip`). `pipx inject`
    is the only way to add a package to an existing pipx install.
    """
    return "pipx" in sys.prefix.lower()


def install_hint(extra: str, packages: tuple[str, ...]) -> str:
    """Return the correct remediation command for however cartographer was installed."""
    if _is_pipx_managed():
        pkg_args = " ".join(f'"{p}"' for p in packages)
        return f"pipx inject cartographer {pkg_args}"
    return f"pip install 'cartographer\\[{extra}]'"
