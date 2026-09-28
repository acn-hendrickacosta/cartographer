"""Central KG driver: Neo4j.

Implements the same logical interface as the local Kuzu driver (kg.py) but
writes to a Neo4j instance via the Bolt protocol. Used only for the global
scope (central topology). Local scope always uses Kuzu.

Requires: neo4j (install with: pip install "cartographer[central]")

Node label:  Artifact
Edge type:   RELATES_TO  (with `type` property carrying the semantic edge type)
"""

from __future__ import annotations

from dataclasses import dataclass

from cartographer.indexing.kg import Edge, Node


@dataclass
class Neo4jDriver:
    uri: str
    user: str
    password: str

    def _driver(self):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise ImportError(
                "neo4j is required for Neo4j support. "
                "Install with: pip install \"cartographer[central]\""
            ) from exc
        return GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def ensure_namespace(self) -> None:
        drv = self._driver()
        try:
            with drv.session() as session:
                session.run(
                    "CREATE CONSTRAINT artifact_id IF NOT EXISTS "
                    "FOR (a:Artifact) REQUIRE a.id IS UNIQUE"
                )
        finally:
            drv.close()

    def upsert_nodes(self, nodes: list[Node]) -> None:
        if not nodes:
            return
        drv = self._driver()
        try:
            with drv.session() as session:
                for node in nodes:
                    session.run(
                        """
                        MERGE (a:Artifact {id: $id})
                        ON CREATE SET a.project_id=$project_id, a.scope=$scope,
                            a.type=$type, a.path=$path, a.attrs=$attrs
                        ON MATCH SET a.project_id=$project_id, a.scope=$scope,
                            a.type=$type, a.path=$path, a.attrs=$attrs
                        """,
                        id=node.id, project_id=node.project_id, scope=node.scope,
                        type=node.type, path=node.path, attrs=node.attrs,
                    )
        finally:
            drv.close()

    def upsert_edges(self, edges: list[Edge]) -> None:
        if not edges:
            return
        drv = self._driver()
        try:
            with drv.session() as session:
                for edge in edges:
                    session.run(
                        """
                        MATCH (s:Artifact {id: $src}), (d:Artifact {id: $dst})
                        MERGE (s)-[r:RELATES_TO {type: $type}]->(d)
                        ON CREATE SET r.scope=$scope, r.attrs=$attrs
                        ON MATCH SET r.scope=$scope, r.attrs=$attrs
                        """,
                        src=edge.src, dst=edge.dst, type=edge.type,
                        scope=edge.scope, attrs=edge.attrs,
                    )
        finally:
            drv.close()

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        drv = self._driver()
        try:
            with drv.session() as session:
                result = session.run(cypher, **(params or {}))
                return [dict(record) for record in result]
        except Exception:
            return []
        finally:
            drv.close()

    def neighbors(self, node_id: str, depth: int = 1, scope: str | None = None) -> list[dict]:
        depth = max(1, min(depth, 4))
        scope_filter = "WHERE r.scope = $scope" if scope else ""
        cypher = (
            f"MATCH (a:Artifact {{id: $id}})-[r:RELATES_TO*1..{depth}]-(n:Artifact) "
            f"{scope_filter} "
            "RETURN DISTINCT n.id AS id, n.type AS type, n.path AS path, n.scope AS scope"
        )
        params: dict = {"id": node_id}
        if scope:
            params["scope"] = scope
        return self.query(cypher, params)

    def delete_nodes(self, ids: list[str]) -> None:
        if not ids:
            return
        drv = self._driver()
        try:
            with drv.session() as session:
                for nid in ids:
                    session.run(
                        "MATCH (a:Artifact {id: $id}) DETACH DELETE a",
                        id=nid,
                    )
        finally:
            drv.close()

    def delete_edges(self, src: str, dst: str, edge_type: str) -> None:
        drv = self._driver()
        try:
            with drv.session() as session:
                session.run(
                    "MATCH (s:Artifact {id: $src})-[r:RELATES_TO {type: $type}]->(d:Artifact {id: $dst}) "
                    "DELETE r",
                    src=src, dst=dst, type=edge_type,
                )
        finally:
            drv.close()

    def namespace_stats(self) -> dict[str, int]:
        drv = self._driver()
        try:
            with drv.session() as session:
                node_result = session.run("MATCH (a:Artifact) RETURN count(*) AS cnt")
                node_count = node_result.single()["cnt"]
                edge_result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(*) AS cnt")
                edge_count = edge_result.single()["cnt"]
                return {"nodes": node_count, "edges": edge_count}
        except Exception:
            return {"nodes": 0, "edges": 0}
        finally:
            drv.close()

    def is_reachable(self) -> bool:
        try:
            drv = self._driver()
            with drv.session() as session:
                session.run("RETURN 1")
            drv.close()
            return True
        except ImportError:
            raise  # let caller surface the missing-package message
        except Exception:
            return False
