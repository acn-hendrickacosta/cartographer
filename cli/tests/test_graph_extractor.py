"""Unit tests for the KG graph extractor."""

from pathlib import Path

import pytest

from cartographer.ingestion import graph_extractor
from cartographer.ingestion.text_extractor import ArtifactType


WORKSPACE = Path("/fake/workspace")


def _extract(path_str: str, text: str, artifact_type: ArtifactType):
    path = WORKSPACE / path_str
    return graph_extractor.extract(
        path=path,
        text=text,
        artifact_type=artifact_type,
        project_id="proj_test",
        scope="local",
        workspace_root=WORKSPACE,
    )


def test_extract_code_creates_module_node():
    result = _extract("src/main.py", "x = 1\n", ArtifactType.CODE)
    assert len(result.nodes) >= 1
    file_node = result.nodes[0]
    assert file_node.type == "module"
    assert file_node.path == "src/main.py"
    assert file_node.project_id == "proj_test"
    assert file_node.scope == "local"


def test_extract_code_creates_symbol_nodes():
    code = "def my_function():\n    pass\n\nclass MyClass:\n    pass\n"
    result = _extract("src/utils.py", code, ArtifactType.CODE)
    node_types = {n.type for n in result.nodes}
    assert "symbol" in node_types
    symbol_names = {n.id for n in result.nodes if n.type == "symbol"}
    # Should have extracted my_function and/or MyClass
    assert any("my_function" in s or "MyClass" in s for s in symbol_names)


def test_extract_code_creates_defines_edges():
    code = "def do_thing():\n    pass\n"
    result = _extract("src/do.py", code, ArtifactType.CODE)
    edge_types = {e.type for e in result.edges}
    assert "defines" in edge_types


def test_extract_doc_creates_doc_node():
    result = _extract("docs/README.md", "# Title\nSome content.", ArtifactType.DOC)
    assert result.nodes[0].type == "doc"


def test_extract_spec_creates_spec_node():
    result = _extract("specs/AUTH_SPEC.md", "# Auth spec", ArtifactType.SPEC)
    assert result.nodes[0].type == "spec"


def test_extract_spec_ref_creates_implements_spec_edge():
    code = "# implements spec AUTH-001\ndef authenticate():\n    pass\n"
    result = _extract("src/auth.py", code, ArtifactType.CODE)
    edge_types = {e.type for e in result.edges}
    assert "implements_spec" in edge_types


def test_extract_relative_import_creates_imports_edge():
    code = "from .utils import helper\n\ndef main():\n    pass\n"
    result = _extract("src/main.py", code, ArtifactType.CODE)
    edge_types = {e.type for e in result.edges}
    assert "imports" in edge_types


def test_extract_no_duplicate_symbols():
    # Same symbol name appearing multiple times should not create duplicate nodes
    code = "def foo():\n    pass\n\ndef foo():  # overloaded\n    return 1\n"
    result = _extract("src/dup.py", code, ArtifactType.CODE)
    symbol_ids = [n.id for n in result.nodes if n.type == "symbol"]
    assert len(symbol_ids) == len(set(symbol_ids))
