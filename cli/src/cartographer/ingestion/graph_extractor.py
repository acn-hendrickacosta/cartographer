"""Extract KG nodes and edges from artifacts.

Produces:
  - One Artifact node per file (type = module | doc | spec)
  - One Artifact node per extracted symbol (type = symbol)
  - Stub nodes for unresolved cross-file callees/parents (type = stub)
  - RelatesTo edges: defines, calls, imports, extends, implements_spec

Structural edges (defines, calls, imports, extends) come from the parser
layer (language-agnostic AST). Semantic edges (implements_spec, depends_on)
come from the LLM enricher when --enrich is passed.

No network calls. No model calls. Pure static analysis.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from cartographer.ingestion import parsers as parser_layer
from cartographer.ingestion.parsers.base import ParseResult
from cartographer.ingestion.text_extractor import ArtifactType
from cartographer.indexing.kg import Edge, Node


# Spec reference patterns — applied to all file types, not just code.
_SPEC_REF_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:implements?|per|see)\s+(?:spec|RFC|ADR)[-:\s]*([\w\-\.]+)", re.IGNORECASE),
    re.compile(r"#\s*(?:spec|requirement|req)[:\s]+([\w\-\.]+)", re.IGNORECASE),
    re.compile(r"SPEC[-_]([\w\-\.]+)", re.IGNORECASE),
]


@dataclass
class ExtractedGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


def _file_node_type(artifact_type: ArtifactType) -> str:
    if artifact_type == ArtifactType.SPEC:
        return "spec"
    if artifact_type == ArtifactType.DOC:
        return "doc"
    return "module"


def _make_artifact_id(path_str: str, symbol: str | None = None, spec_id: str | None = None) -> str:
    from cartographer.artifact_id import artifact_id
    return artifact_id(path_str, symbol, spec_id=spec_id)


def extract(
    path: Path,
    text: str,
    artifact_type: ArtifactType,
    project_id: str,
    scope: str,
    workspace_root: Path,
    enrich: bool = False,
) -> ExtractedGraph:
    """Extract KG nodes and edges from a single file."""
    rel_path = str(path.relative_to(workspace_root))
    file_node_id = _make_artifact_id(rel_path)

    attrs: dict = {"artifact_type": artifact_type.value}
    nodes: list[Node] = []
    edges: list[Edge] = []

    if artifact_type == ArtifactType.CODE:
        parse_result = parser_layer.parse(path, text, rel_path)
        _emit_from_parse_result(
            parse_result, rel_path, project_id, scope, file_node_id, nodes, edges
        )

    _extract_spec_refs(text, rel_path, scope, file_node_id, edges)

    if enrich:
        from cartographer.ingestion.kg_enricher import enrich as _enrich
        result = _enrich(rel_path, text)
        if result.summary:
            attrs["summary"] = result.summary
        _merge_enrichment(result, rel_path, project_id, scope, file_node_id, nodes, edges)

    # File node goes first so edges to it always have a valid src.
    nodes.insert(
        0,
        Node(
            id=file_node_id,
            project_id=project_id,
            scope=scope,
            type=_file_node_type(artifact_type),
            path=rel_path,
            attrs=json.dumps(attrs),
        ),
    )

    return ExtractedGraph(nodes=nodes, edges=edges)


def _stub_node(node_id: str, project_id: str, scope: str, path: str, symbol: str) -> Node:
    return Node(
        id=node_id,
        project_id=project_id,
        scope=scope,
        type="stub",
        path=path,
        attrs=json.dumps({"symbol": symbol}),
    )


def _emit_from_parse_result(
    pr: ParseResult,
    rel_path: str,
    project_id: str,
    scope: str,
    file_node_id: str,
    nodes: list[Node],
    edges: list[Edge],
) -> None:
    """Convert a ParseResult into KG nodes and edges."""
    seen_symbol_ids: set[str] = set()

    # symbols → Node(type=symbol) + Edge(defines)
    for sym in pr.symbols:
        sym_id = _make_artifact_id(rel_path, sym.name)
        if sym_id in seen_symbol_ids:
            continue
        seen_symbol_ids.add(sym_id)
        nodes.append(Node(
            id=sym_id,
            project_id=project_id,
            scope=scope,
            type="symbol",
            path=rel_path,
            attrs=json.dumps({"symbol": sym.name, "kind": sym.kind, "line": sym.line}),
        ))
        edges.append(Edge(src=file_node_id, dst=sym_id, type="defines", scope=scope))

    # calls → Edge(calls) from caller symbol → callee symbol (stub if cross-file)
    seen_call_edges: set[tuple[str, str]] = set()
    for call in pr.calls:
        caller_id = _make_artifact_id(rel_path, call.caller)
        callee_file = call.callee_module or rel_path
        callee_id = _make_artifact_id(callee_file, call.callee)
        key = (caller_id, callee_id)
        if key in seen_call_edges:
            continue
        seen_call_edges.add(key)
        # Ensure the callee node exists — create a stub if it's cross-file.
        if callee_file != rel_path and callee_id not in seen_symbol_ids:
            nodes.append(_stub_node(callee_id, project_id, scope, callee_file, call.callee))
            seen_symbol_ids.add(callee_id)
        edges.append(Edge(src=caller_id, dst=callee_id, type="calls", scope=scope))

    # imports → Edge(imports) from file node → module file node (stub)
    seen_import_ids: set[str] = set()
    for imp in pr.imports:
        mod_id = _make_artifact_id(imp.module)
        if mod_id in seen_import_ids:
            continue
        seen_import_ids.add(mod_id)
        nodes.append(Node(
            id=mod_id,
            project_id=project_id,
            scope=scope,
            type="stub",
            path=imp.module,
            attrs=json.dumps({"names": imp.names}),
        ))
        edges.append(Edge(src=file_node_id, dst=mod_id, type="imports", scope=scope))

    # extends → Edge(extends) from child symbol → parent symbol (stub if cross-file)
    for ext in pr.extends:
        child_id = _make_artifact_id(rel_path, ext.child)
        parent_file = ext.parent_module or rel_path
        parent_id = _make_artifact_id(parent_file, ext.parent)
        if parent_file != rel_path and parent_id not in seen_symbol_ids:
            nodes.append(_stub_node(parent_id, project_id, scope, parent_file, ext.parent))
            seen_symbol_ids.add(parent_id)
        edges.append(Edge(src=child_id, dst=parent_id, type="extends", scope=scope))


def _concept_node(name: str, project_id: str, scope: str) -> Node:
    node_id = _make_artifact_id(f"concept://{name}")
    return Node(
        id=node_id,
        project_id=project_id,
        scope=scope,
        type="concept",
        path=f"concept://{name}",
        attrs=json.dumps({"name": name}),
    )


def _merge_enrichment(
    result,
    rel_path: str,
    project_id: str,
    scope: str,
    file_node_id: str,
    nodes: list[Node],
    edges: list[Edge],
) -> None:
    for spec_name in result.implements:
        stub = _concept_node(spec_name, project_id, scope)
        nodes.append(stub)
        edges.append(Edge(src=file_node_id, dst=stub.id, type="implements_spec", scope=scope))

    for dep_name in result.depends_on:
        stub = _concept_node(dep_name, project_id, scope)
        nodes.append(stub)
        edges.append(Edge(src=file_node_id, dst=stub.id, type="depends_on", scope=scope))

    for rel in result.relationships:
        rel_type = str(rel.get("type", "relates_to"))
        target = str(rel.get("target", ""))
        if not target:
            continue
        stub = _concept_node(target, project_id, scope)
        nodes.append(stub)
        edges.append(Edge(src=file_node_id, dst=stub.id, type=rel_type, scope=scope))


def _extract_spec_refs(
    text: str,
    rel_path: str,
    scope: str,
    file_node_id: str,
    edges: list[Edge],
) -> None:
    for pat in _SPEC_REF_PATTERNS:
        for m in pat.finditer(text):
            spec_id = m.group(1).strip()
            dst_id = _make_artifact_id("", spec_id=spec_id)
            edges.append(Edge(src=file_node_id, dst=dst_id, type="implements_spec", scope=scope))
