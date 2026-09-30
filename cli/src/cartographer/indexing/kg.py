"""Local KG driver: an embedded Kuzu property graph.

Schema per PROJECT_BRIEF.md Section 7.2, kept deliberately small: a single generic
`Artifact` node table and a single generic `RelatesTo` edge table, with `type` carried
as a property rather than modeled as separate relationship tables per edge kind. Add
edge types only when a recall query actually needs them (Section 7.2 says so
explicitly) -- this is a driver detail, not a schema decision to revisit lightly.

Writing this as a small, reusable driver (rather than inline in commands/) is
deliberate: the future MCP `kg` server (Section 6.5) is meant to reuse this same
on-disk database and the same upsert semantics instead of reimplementing them.
"""

from __future__ import annotations

from pathlib import Path

import kuzu
from pydantic import BaseModel

Scope = str  # "local" | "global"


class Node(BaseModel):
    id: str  # artifact identity, see artifact_id.py
    project_id: str
    scope: Scope
    type: str  # module | symbol | spec | doc
    path: str
    attrs: str = "{}"  # JSON-encoded, kept as a string to avoid a nested schema


class Edge(BaseModel):
    src: str
    dst: str
    type: str  # defines | references | implements_spec | depends_on
    scope: Scope
    attrs: str = "{}"


def _connect(db_path: Path) -> kuzu.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(db_path))
    return kuzu.Connection(db)


def _create_if_absent(conn: kuzu.Connection, ddl: str) -> None:
    try:
        conn.execute(ddl)
    except RuntimeError as exc:
        if "already exists" not in str(exc).lower():
            raise


def ensure_namespace(db_path: Path) -> None:
    """Create the Artifact/RelatesTo schema if this is a fresh database. Idempotent."""
    conn = _connect(db_path)
    _create_if_absent(
        conn,
        "CREATE NODE TABLE Artifact("
        "id STRING, project_id STRING, scope STRING, type STRING, path STRING, attrs STRING, "
        "PRIMARY KEY (id))",
    )
    _create_if_absent(
        conn,
        "CREATE REL TABLE RelatesTo("
        "FROM Artifact TO Artifact, type STRING, scope STRING, attrs STRING)",
    )


def upsert_nodes(db_path: Path, nodes: list[Node]) -> None:
    conn = _connect(db_path)
    for node in nodes:
        conn.execute(
            "MERGE (a:Artifact {id: $id}) "
            "ON CREATE SET a.project_id=$project_id, a.scope=$scope, a.type=$type, "
            "a.path=$path, a.attrs=$attrs "
            "ON MATCH SET a.project_id=$project_id, a.scope=$scope, a.type=$type, "
            "a.path=$path, a.attrs=$attrs",
            {
                "id": node.id,
                "project_id": node.project_id,
                "scope": node.scope,
                "type": node.type,
                "path": node.path,
                "attrs": node.attrs,
            },
        )


def upsert_edges(db_path: Path, edges: list[Edge]) -> None:
    conn = _connect(db_path)
    for edge in edges:
        conn.execute(
            "MATCH (s:Artifact {id: $src}), (d:Artifact {id: $dst}) "
            "MERGE (s)-[r:RelatesTo {type: $type}]->(d) "
            "ON CREATE SET r.scope=$scope, r.attrs=$attrs "
            "ON MATCH SET r.scope=$scope, r.attrs=$attrs",
            {
                "src": edge.src,
                "dst": edge.dst,
                "type": edge.type,
                "scope": edge.scope,
                "attrs": edge.attrs,
            },
        )


def _rows(result) -> list[dict]:
    columns = result.get_column_names()
    rows = []
    while result.has_next():
        rows.append(dict(zip(columns, result.get_next())))
    return rows


def query(db_path: Path, cypher: str, params: dict | None = None) -> list[dict]:
    """Escape hatch for arbitrary read queries (recall, doctor)."""
    conn = _connect(db_path)
    result = conn.execute(cypher, params or {})
    return _rows(result)


def neighbors(db_path: Path, node_id: str, depth: int = 1, scope: str | None = None) -> list[dict]:
    depth = max(1, min(depth, 6))
    # r is a RECURSIVE_REL for variable-length patterns; scope lives on each hop,
    # so filter via rels(r), not r directly (r.scope is not a valid accessor).
    # Kuzu's binder can't resolve a $param inside this ALL(...) predicate (KU_UNREACHABLE
    # assertion), so the scope value is validated and inlined as a literal instead.
    scope_filter = ""
    if scope:
        if scope not in ("local", "global"):
            raise ValueError(f"invalid scope: {scope!r}")
        scope_filter = f"WHERE ALL(rel IN rels(r) WHERE rel.scope = '{scope}')"
    cypher = (
        f"MATCH (a:Artifact {{id: $id}})-[r:RelatesTo* 1..{depth}]-(n:Artifact) "
        f"{scope_filter} "
        "RETURN DISTINCT n.id AS id, n.type AS type, n.path AS path, n.scope AS scope"
    )
    return query(db_path, cypher, {"id": node_id})


def delete_by_path(kg_path: Path, path: str) -> None:
    """Detach-delete all Artifact nodes for the given path from the local KG."""
    if not kg_path.exists():
        return
    conn = _connect(kg_path)
    conn.execute("MATCH (a:Artifact) WHERE a.path = $path DETACH DELETE a", {"path": path})


def is_readable(db_path: Path) -> bool:
    """doctor helper: confirm the database directory opens without error."""
    try:
        _connect(db_path)
        return True
    except Exception:
        return False
