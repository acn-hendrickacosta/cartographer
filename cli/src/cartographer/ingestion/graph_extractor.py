"""Extract KG nodes and edges from artifacts.

Produces:
  - One Artifact node per file (type = module | doc | spec)
  - One Artifact node per extracted symbol (type = symbol)
  - RelatesTo edges: defines, references, implements_spec, depends_on

Edge extraction is heuristic. Confidence signals per components/skills.md:
  1. import/require/use statement  -> depends_on (high confidence)
  2. Explicit spec reference in comment or docstring -> implements_spec (high)
  3. Symbol name matches a spec section heading -> implements_spec (medium)
  4. Co-location in the same file -> defines (high, structural)

No network calls. No model calls. Pure static analysis.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from cartographer.ingestion.text_extractor import ArtifactType
from cartographer.indexing.kg import Edge, Node


# --- Import/dependency patterns ---

_IMPORT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^import\s+([\w\.]+)", re.MULTILINE),           # Python: import x.y
    re.compile(r"^from\s+([\w\.]+)\s+import", re.MULTILINE),    # Python: from x import y
    re.compile(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?"""),  # JS/TS: import 'x' or require('x')
    re.compile(r"^use\s+([\w:]+)", re.MULTILINE),               # Rust: use x::y
    re.compile(r'^import\s+"([^"]+)"', re.MULTILINE),           # Go: import "pkg"
]

# --- Spec reference patterns ---

_SPEC_REF_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:implements?|per|see)\s+(?:spec|RFC|ADR)[-:\s]*([\w\-\.]+)", re.IGNORECASE),
    re.compile(r"#\s*(?:spec|requirement|req)[:\s]+([\w\-\.]+)", re.IGNORECASE),
    re.compile(r"SPEC[-_]([\w\-\.]+)", re.IGNORECASE),
]

# --- Symbol definition patterns (same as chunker, single pass) ---

_DEF_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(?:async\s+)?def\s+(\w+)", re.MULTILINE),
    re.compile(r"^class\s+(\w+)", re.MULTILINE),
    re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE),
    re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=", re.MULTILINE),
    re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE),
    re.compile(r"^func\s+(\w+)", re.MULTILINE),
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
) -> ExtractedGraph:
    """Extract KG nodes and edges from a single file."""
    rel_path = str(path.relative_to(workspace_root))
    file_node_id = _make_artifact_id(rel_path)

    nodes: list[Node] = [
        Node(
            id=file_node_id,
            project_id=project_id,
            scope=scope,
            type=_file_node_type(artifact_type),
            path=rel_path,
            attrs=json.dumps({"artifact_type": artifact_type.value}),
        )
    ]
    edges: list[Edge] = []

    if artifact_type == ArtifactType.CODE:
        _extract_symbols(text, rel_path, project_id, scope, file_node_id, nodes, edges)
        _extract_imports(text, rel_path, project_id, scope, file_node_id, edges, workspace_root)

    _extract_spec_refs(text, rel_path, scope, file_node_id, edges)

    return ExtractedGraph(nodes=nodes, edges=edges)


def _extract_symbols(
    text: str,
    rel_path: str,
    project_id: str,
    scope: str,
    file_node_id: str,
    nodes: list[Node],
    edges: list[Edge],
) -> None:
    seen: set[str] = set()
    for pat in _DEF_PATTERNS:
        for m in pat.finditer(text):
            # Top-level only (no leading indent)
            line_start = text.rfind("\n", 0, m.start()) + 1
            if len(text[line_start : m.start()]) > 0:
                continue
            symbol = m.group(1)
            if symbol in seen:
                continue
            seen.add(symbol)
            sym_id = _make_artifact_id(rel_path, symbol)
            nodes.append(
                Node(
                    id=sym_id,
                    project_id=project_id,
                    scope=scope,
                    type="symbol",
                    path=rel_path,
                    attrs=json.dumps({"symbol": symbol}),
                )
            )
            edges.append(
                Edge(src=file_node_id, dst=sym_id, type="defines", scope=scope)
            )


def _extract_imports(
    text: str,
    rel_path: str,
    project_id: str,
    scope: str,
    file_node_id: str,
    edges: list[Edge],
    workspace_root: Path,
) -> None:
    for pat in _IMPORT_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            # Relative imports only — skip stdlib and third-party
            if not (raw.startswith(".") or raw.startswith("cartographer")):
                continue
            # Normalise to a local file ID heuristic; edges to missing nodes are fine
            dep_path = raw.replace(".", "/").lstrip("/")
            dst_id = _make_artifact_id(dep_path)
            edges.append(
                Edge(src=file_node_id, dst=dst_id, type="depends_on", scope=scope)
            )


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
            edges.append(
                Edge(src=file_node_id, dst=dst_id, type="implements_spec", scope=scope)
            )
