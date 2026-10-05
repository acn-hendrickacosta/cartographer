"""Phase 4: kg_impact — reverse-traversal impact analysis.

Covers the local Kuzu path (kg.impact), the MCP tool wrapper's local-scope
dispatch and error handling, and the full MCP tool wrapper against a real
local KG. The global (Neo4j) path — kg_neo4j.Neo4jDriver.find_impact — is
exercised in test_central_drivers.py's integration tests, consistent with
how every other central-driver method in this project is tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cartographer.indexing import kg as kg_driver
from cartographer.indexing.kg import Edge, Node
from cartographer.runtime.mcp_servers import kg_server


def _node(path: str, project_id: str = "proj") -> Node:
    return Node(id=f"path:{path}", project_id=project_id, scope="local", type="module", path=path, attrs="{}")


def _seed_chain(kg_path: Path) -> None:
    """a.py <-imports- b.py <-imports- c.py (c depends on b depends on a)."""
    kg_driver.ensure_namespace(kg_path)
    a, b, c = _node("a.py"), _node("b.py"), _node("c.py")
    kg_driver.upsert_nodes(kg_path, [a, b, c])
    kg_driver.upsert_edges(kg_path, [
        Edge(src=b.id, dst=a.id, type="imports", scope="local", attrs="{}"),
        Edge(src=c.id, dst=b.id, type="imports", scope="local", attrs="{}"),
    ])


# ---------------------------------------------------------------------------
# kg.impact() — local Kuzu driver
# ---------------------------------------------------------------------------

def test_impact_finds_transitive_dependents(tmp_path):
    kg_path = tmp_path / "kg.kuzu"
    _seed_chain(kg_path)

    rows = kg_driver.impact(kg_path, "path:a.py", depth=4, edge_types=["imports"])
    paths_by_distance = {r["path"]: r["distance"] for r in rows}

    assert paths_by_distance == {"b.py": 1, "c.py": 2}


def test_impact_respects_edge_type_filter(tmp_path):
    """An edge type not in the filter list must not be traversed."""
    kg_path = tmp_path / "kg.kuzu"
    kg_driver.ensure_namespace(kg_path)
    a, b = _node("a.py"), _node("b.py")
    kg_driver.upsert_nodes(kg_path, [a, b])
    kg_driver.upsert_edges(kg_path, [Edge(src=b.id, dst=a.id, type="calls", scope="local", attrs="{}")])

    rows = kg_driver.impact(kg_path, "path:a.py", depth=4, edge_types=["imports"])
    assert rows == []


def test_impact_defaults_to_calls_imports_extends(tmp_path):
    kg_path = tmp_path / "kg.kuzu"
    kg_driver.ensure_namespace(kg_path)
    a, b = _node("a.py"), _node("b.py")
    kg_driver.upsert_nodes(kg_path, [a, b])
    kg_driver.upsert_edges(kg_path, [Edge(src=b.id, dst=a.id, type="extends", scope="local", attrs="{}")])

    rows = kg_driver.impact(kg_path, "path:a.py")
    assert len(rows) == 1
    assert rows[0]["path"] == "b.py"


def test_impact_rejects_invalid_edge_type(tmp_path):
    """edge_types is inlined as a Cypher literal (Kuzu binder limitation) —
    must be validated against a strict identifier pattern first."""
    kg_path = tmp_path / "kg.kuzu"
    kg_driver.ensure_namespace(kg_path)

    with pytest.raises(ValueError):
        kg_driver.impact(kg_path, "path:a.py", edge_types=["imports'; MATCH (n) DETACH DELETE n; //"])


def test_impact_no_dependents_returns_empty(tmp_path):
    kg_path = tmp_path / "kg.kuzu"
    kg_driver.ensure_namespace(kg_path)
    kg_driver.upsert_nodes(kg_path, [_node("isolated.py")])

    assert kg_driver.impact(kg_path, "path:isolated.py") == []


# ---------------------------------------------------------------------------
# kg_impact MCP tool — local scope dispatch and error handling
# ---------------------------------------------------------------------------

def test_kg_impact_tool_local_scope(tmp_path, monkeypatch):
    workspace = tmp_path / "proj"
    kg_path = workspace / ".cartographer" / "local" / "kg.kuzu"
    kg_path.parent.mkdir(parents=True)
    _seed_chain(kg_path)

    result = kg_server.kg_impact(
        node_id="path:a.py", workspace=str(workspace), edge_types="imports", scope="local",
    )
    import json
    data = json.loads(result)

    assert data["scope"] == "local"
    paths = {r["path"] for r in data["impact"]}
    assert paths == {"b.py", "c.py"}


def test_kg_impact_tool_local_scope_missing_kg_returns_error(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()

    result = kg_server.kg_impact(node_id="path:a.py", workspace=str(workspace), scope="local")
    import json
    data = json.loads(result)

    assert "error" in data


def test_kg_impact_tool_global_scope_requires_central_topology(tmp_path, monkeypatch):
    from cartographer import config as config_mod

    workspace = tmp_path / "proj"
    workspace.mkdir()
    cfg = config_mod.CartographerConfig(
        project=config_mod.ProjectSection(id="proj_x", name="x"),
        topology=config_mod.TopologySection(mode="local"),
    )
    config_mod.save_config(workspace, cfg)

    result = kg_server.kg_impact(node_id="path:a.py", workspace=str(workspace), scope="global")
    import json
    data = json.loads(result)

    assert "error" in data
    assert "central" in data["error"].lower()
