"""Python AST parser — uses stdlib ast, no extra dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

from cartographer.ingestion.parsers.base import (
    CallEdge,
    ExtendsEdge,
    ImportEdge,
    ParseResult,
    SymbolDef,
)

# Names not worth emitting as call edges — too noisy, no graph value.
_SKIP_CALLEES: frozenset[str] = frozenset(
    "print len range type str int float list dict set tuple bool "
    "isinstance issubclass hasattr getattr setattr delattr callable "
    "iter next enumerate zip map filter sorted reversed any all sum "
    "min max abs round repr open super object property classmethod "
    "staticmethod vars dir id hash input format chr ord hex oct bin "
    "ValueError TypeError KeyError IndexError AttributeError "
    "RuntimeError NotImplementedError StopIteration "
    "append extend insert remove pop clear update get items keys values "
    "join split strip lstrip rstrip lower upper replace encode decode "
    "format startswith endswith".split()
)


def _module_to_rel_path(module: str, rel_path: str, level: int) -> str:
    """Convert an import module string to a workspace-relative file path.

    level > 0 means a relative import (from . import x, from .. import y).
    """
    base = Path(rel_path)
    if level > 0:
        # Walk up `level` directories from the current file's directory.
        anchor = base.parent
        for _ in range(level - 1):
            anchor = anchor.parent
        if module:
            return str(anchor / module.replace(".", "/")) + ".py"
        return str(anchor / "__init__.py")
    # Absolute import: treat as a path relative to the project root.
    return module.replace(".", "/") + ".py"


class PythonParser:
    def parse(self, text: str, path: Path, rel_path: str) -> ParseResult:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ParseResult()

        result = ParseResult()
        import_map: dict[str, str] = {}  # name → resolved rel path

        # First pass: collect imports to build the resolution map.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                level = node.level or 0
                mod = node.module or ""
                resolved = _module_to_rel_path(mod, rel_path, level)
                for alias in node.names or []:
                    name = alias.asname or alias.name
                    import_map[name] = resolved
                result.imports.append(ImportEdge(
                    module=resolved,
                    names=[a.asname or a.name for a in (node.names or [])],
                ))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    resolved = alias.name.replace(".", "/") + ".py"
                    import_map[alias.asname or alias.name] = resolved
                    import_map[top] = alias.name.replace(".", "/") + "/__init__.py"
                    result.imports.append(ImportEdge(
                        module=resolved,
                        names=[alias.asname or alias.name],
                    ))

        # Second pass: collect symbols (defs) and their call sites.
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                result.symbols.append(SymbolDef(
                    name=node.name, kind="class", line=node.lineno,
                ))
                for base in node.bases:
                    parent_name: str | None = None
                    parent_mod = ""
                    if isinstance(base, ast.Name):
                        parent_name = base.id
                        parent_mod = import_map.get(parent_name, "")
                    elif isinstance(base, ast.Attribute):
                        parent_name = base.attr
                        if isinstance(base.value, ast.Name):
                            parent_mod = import_map.get(base.value.id, "")
                    if parent_name:
                        result.extends.append(ExtendsEdge(
                            child=node.name,
                            parent=parent_name,
                            parent_module=parent_mod,
                        ))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if _is_method(node, tree) else "function"
                result.symbols.append(SymbolDef(
                    name=node.name, kind=kind, line=node.lineno,
                ))
                seen_callees: set[str] = set()
                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue
                    callee_name: str | None = None
                    callee_mod = ""
                    if isinstance(child.func, ast.Name):
                        callee_name = child.func.id
                        callee_mod = import_map.get(callee_name, "")
                    elif isinstance(child.func, ast.Attribute):
                        callee_name = child.func.attr
                        if isinstance(child.func.value, ast.Name):
                            obj = child.func.value.id
                            callee_mod = import_map.get(obj, "")
                    if (
                        callee_name
                        and callee_name not in _SKIP_CALLEES
                        and callee_name not in seen_callees
                    ):
                        seen_callees.add(callee_name)
                        result.calls.append(CallEdge(
                            caller=node.name,
                            callee=callee_name,
                            callee_module=callee_mod,
                            line=child.lineno if hasattr(child, "lineno") else 0,
                        ))

        return result


def _is_method(fn_node: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.AST) -> bool:
    """Return True if fn_node is directly inside a ClassDef body."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if item is fn_node:
                    return True
    return False
