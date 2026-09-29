"""TypeScript/TSX parser — uses tree-sitter-typescript (optional extra: parsers-ts).

Mirrors python_parser.py's structure and simplifications (e.g. calls are
attributed to the nearest enclosing named symbol found during a top-level
scan, not a fully scope-aware resolver; symbol identity is the bare name,
matching PythonParser's `_make_artifact_id(rel_path, name)` convention).
"""

from __future__ import annotations

import posixpath
from pathlib import Path

import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser as TSParser

from cartographer.ingestion.parsers.base import (
    CallEdge,
    ExtendsEdge,
    ImportEdge,
    ParseResult,
    SymbolDef,
)

_TS_LANGUAGE = Language(tsts.language_typescript())
_TSX_LANGUAGE = Language(tsts.language_tsx())

# Globals not worth emitting as call edges — too noisy, no graph value.
_SKIP_CALLEES: frozenset[str] = frozenset(
    "log warn error info debug trace assert require "
    "String Number Boolean Array Object Set Map Promise Symbol "
    "parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent "
    "setTimeout setInterval clearTimeout clearInterval "
    "isArray from of keys values entries assign freeze stringify parse "
    "map filter reduce forEach find findIndex some every includes push pop "
    "slice splice concat join split indexOf toString valueOf "
    "then catch finally bind call apply".split()
)


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8") if node is not None and node.text else ""


def _resolve_module(raw: str, rel_path: str) -> str:
    """Relative specifier ('./x', '../y') -> workspace-relative file path.

    Bare package specifiers (no leading dot) are npm packages, not local
    files — the caller should skip those rather than resolving them.
    """
    anchor = Path(rel_path).parent.as_posix()
    joined = posixpath.join(anchor, raw)
    # posixpath.normpath collapses ./ and ../ segments as pure string ops —
    # no filesystem access, unlike Path.resolve().
    resolved = posixpath.normpath(joined)
    if not any(resolved.endswith(s) for s in (".ts", ".tsx", ".js", ".jsx")):
        resolved += ".ts"
    return resolved


class TypeScriptParser:
    def parse(self, text: str, path: Path, rel_path: str) -> ParseResult:
        language = _TSX_LANGUAGE if path.suffix.lower() == ".tsx" else _TS_LANGUAGE
        parser = TSParser(language)
        tree = parser.parse(text.encode("utf-8"))
        root = tree.root_node

        result = ParseResult()
        import_map: dict[str, str] = {}

        self._collect_imports(root, rel_path, result, import_map)
        self._collect_symbols(root, rel_path, result, import_map)
        return result

    def _collect_imports(
        self, root: Node, rel_path: str, result: ParseResult, import_map: dict[str, str]
    ) -> None:
        for node in _walk(root):
            if node.type not in ("import_statement", "export_statement"):
                continue
            source = node.child_by_field_name("source")
            if source is None:
                continue
            raw = _text(source).strip("'\"")
            if not raw.startswith("."):
                continue  # bare package specifier — not a local file
            resolved = _resolve_module(raw, rel_path)

            names: list[str] = []
            clause = node.child_by_field_name("import_clause") or _first_child_of_type(
                node, "import_clause"
            )
            if clause is not None:
                for child in clause.named_children:
                    if child.type == "identifier":
                        names.append(_text(child))
                        import_map[_text(child)] = resolved
                    elif child.type == "namespace_import":
                        ident = _first_child_of_type(child, "identifier")
                        if ident is not None:
                            names.append(_text(ident))
                            import_map[_text(ident)] = resolved
                    elif child.type == "named_imports":
                        for spec in child.named_children:
                            if spec.type != "import_specifier":
                                continue
                            name_node = spec.child_by_field_name("name")
                            alias_node = spec.child_by_field_name("alias")
                            local = _text(alias_node) if alias_node is not None else _text(name_node)
                            if local:
                                names.append(local)
                                import_map[local] = resolved
            result.imports.append(ImportEdge(module=resolved, names=names))

    def _collect_symbols(
        self, root: Node, rel_path: str, result: ParseResult, import_map: dict[str, str]
    ) -> None:
        seen: set[str] = set()

        for node in _walk(root):
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node)
                if name in seen:
                    continue
                seen.add(name)
                result.symbols.append(SymbolDef(name=name, kind="function", line=node.start_point[0] + 1))
                self._collect_calls(node, name, result, import_map)

            elif node.type == "variable_declarator":
                # `const foo = () => {...}` / `const foo = function() {...}`
                value = node.child_by_field_name("value")
                if value is None or value.type not in ("arrow_function", "function_expression"):
                    continue
                name_node = node.child_by_field_name("name")
                if name_node is None or name_node.type != "identifier":
                    continue
                name = _text(name_node)
                if name in seen:
                    continue
                seen.add(name)
                result.symbols.append(SymbolDef(name=name, kind="function", line=node.start_point[0] + 1))
                self._collect_calls(value, name, result, import_map)

            elif node.type in ("class_declaration", "interface_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node is None:
                    continue
                name = _text(name_node)
                result.symbols.append(SymbolDef(name=name, kind="class", line=node.start_point[0] + 1))
                self._collect_heritage(node, name, rel_path, result, import_map)

                body = node.child_by_field_name("body")
                if body is not None:
                    for member in body.named_children:
                        if member.type != "method_definition":
                            continue
                        m_name_node = member.child_by_field_name("name")
                        if m_name_node is None:
                            continue
                        m_name = _text(m_name_node)
                        if m_name in seen:
                            continue
                        seen.add(m_name)
                        result.symbols.append(
                            SymbolDef(name=m_name, kind="method", line=member.start_point[0] + 1)
                        )
                        self._collect_calls(member, m_name, result, import_map)

    def _collect_heritage(
        self, node: Node, child_name: str, rel_path: str, result: ParseResult, import_map: dict[str, str]
    ) -> None:
        if node.type == "class_declaration":
            heritage = _first_child_of_type(node, "class_heritage")
            if heritage is None:
                return
            extends_clause = _first_child_of_type(heritage, "extends_clause")
            if extends_clause is None:
                return
            value = extends_clause.child_by_field_name("value")
            parent = _identifier_name(value)
            if parent:
                result.extends.append(
                    ExtendsEdge(child=child_name, parent=parent, parent_module=import_map.get(parent, ""))
                )
        else:  # interface_declaration — can extend multiple interfaces
            extends_clause = _first_child_of_type(node, "extends_type_clause")
            if extends_clause is None:
                return
            for type_node in extends_clause.named_children:
                if type_node.type != "type_identifier":
                    continue
                parent = _text(type_node)
                result.extends.append(
                    ExtendsEdge(child=child_name, parent=parent, parent_module=import_map.get(parent, ""))
                )

    def _collect_calls(
        self, scope_node: Node, caller: str, result: ParseResult, import_map: dict[str, str]
    ) -> None:
        seen_callees: set[str] = set()
        for node in _walk(scope_node):
            if node.type != "call_expression":
                continue
            fn = node.child_by_field_name("function")
            callee_name: str | None = None
            callee_module = ""
            if fn is None:
                continue
            if fn.type == "identifier":
                callee_name = _text(fn)
                callee_module = import_map.get(callee_name, "")
            elif fn.type == "member_expression":
                prop = fn.child_by_field_name("property")
                obj = fn.child_by_field_name("object")
                callee_name = _text(prop)
                if obj is not None and obj.type == "identifier":
                    callee_module = import_map.get(_text(obj), "")
            if callee_name and callee_name not in _SKIP_CALLEES and callee_name not in seen_callees:
                seen_callees.add(callee_name)
                result.calls.append(
                    CallEdge(
                        caller=caller,
                        callee=callee_name,
                        callee_module=callee_module,
                        line=node.start_point[0] + 1,
                    )
                )


def _identifier_name(node: Node | None) -> str:
    """Base class name from an `extends` value — identifier or a.b.C member chain."""
    if node is None:
        return ""
    if node.type == "identifier":
        return _text(node)
    if node.type == "member_expression":
        prop = node.child_by_field_name("property")
        return _text(prop)
    return ""


def _first_child_of_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _walk(node: Node):
    """Depth-first traversal, including `node` itself."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))
