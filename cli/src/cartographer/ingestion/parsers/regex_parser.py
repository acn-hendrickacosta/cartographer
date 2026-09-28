"""Regex-based fallback parser for unsupported languages.

Wraps the original import and symbol extraction patterns from graph_extractor.
Returns symbols and imports only — calls and extends are left empty (regex
cannot reliably detect these without a real parse tree).
"""

from __future__ import annotations

import re
from pathlib import Path

from cartographer.ingestion.parsers.base import (
    ImportEdge,
    ParseResult,
    SymbolDef,
)

_IMPORT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^import\s+([\w\.]+)", re.MULTILINE),
    re.compile(r"^from\s+([\w\.]+)\s+import", re.MULTILINE),
    re.compile(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?"""),
    re.compile(r"^use\s+([\w:]+)", re.MULTILINE),
    re.compile(r'^import\s+"([^"]+)"', re.MULTILINE),
]

_DEF_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(?:async\s+)?def\s+(\w+)", re.MULTILINE),
    re.compile(r"^class\s+(\w+)", re.MULTILINE),
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
    re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=", re.MULTILINE),
    re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE),
    re.compile(r"^func\s+(\w+)", re.MULTILINE),
]


class RegexParser:
    def parse(self, text: str, path: Path, rel_path: str) -> ParseResult:
        result = ParseResult()
        seen_symbols: set[str] = set()

        for pat in _DEF_PATTERNS:
            for m in pat.finditer(text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                if len(text[line_start : m.start()]) > 0:
                    continue  # top-level only
                name = m.group(1)
                if name not in seen_symbols:
                    seen_symbols.add(name)
                    kind = "class" if "class" in pat.pattern else "function"
                    result.symbols.append(SymbolDef(
                        name=name,
                        kind=kind,
                        line=text[: m.start()].count("\n") + 1,
                    ))

        for pat in _IMPORT_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group(1).strip()
                if not (raw.startswith(".") or raw.startswith("cartographer")):
                    continue
                dep_path = raw.replace(".", "/").lstrip("/") + ".py"
                result.imports.append(ImportEdge(module=dep_path, names=[]))

        return result
