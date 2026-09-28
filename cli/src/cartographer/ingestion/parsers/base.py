"""Language-agnostic parse result types and Parser protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class SymbolDef:
    name: str
    kind: str   # "function" | "method" | "class"
    line: int   # 1-indexed


@dataclass
class CallEdge:
    caller: str         # name of the containing function/method
    callee: str         # name of the function being called
    callee_module: str  # resolved relative file path, or "" = same file / unresolved
    line: int


@dataclass
class ImportEdge:
    module: str         # workspace-relative file path (e.g. "src/config.py")
    names: list[str]    # imported names; empty = module-level import


@dataclass
class ExtendsEdge:
    child: str          # class doing the inheriting
    parent: str         # base class name
    parent_module: str  # resolved relative file path, or "" = same file / unresolved


@dataclass
class ParseResult:
    symbols: list[SymbolDef]  = field(default_factory=list)
    calls:   list[CallEdge]   = field(default_factory=list)
    imports: list[ImportEdge] = field(default_factory=list)
    extends: list[ExtendsEdge]= field(default_factory=list)


class Parser(Protocol):
    def parse(self, text: str, path: Path, rel_path: str) -> ParseResult: ...
