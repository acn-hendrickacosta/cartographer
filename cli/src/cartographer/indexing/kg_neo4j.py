"""Central KG driver: Neo4j.

Implements the same logical interface as the local Kuzu driver (kg.py) but
writes to a Neo4j instance via the Bolt protocol. Used only for the global
scope (central topology). Local scope always uses Kuzu.

Requires: neo4j (install with: pip install "cartographer[central]")

Node label:  Artifact
Edge type:   RELATES_TO  (with `type` property carrying the semantic edge type)
"""

from __future__ import annotations

import json
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

    def query_raising(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Same as query(), but propagates exceptions instead of swallowing
        them to []. query()'s silent-degrade-to-empty contract is relied on
        by recall.py/gc.py/promote.py; this exists only for kg_search's retry
        loop, which needs to distinguish "the query failed" from "the query
        succeeded and legitimately found nothing" — query() makes those two
        cases indistinguishable on purpose, which is exactly the wrong
        behavior for deciding whether to retry Claude-generated Cypher."""
        drv = self._driver()
        try:
            with drv.session() as session:
                result = session.run(cypher, **(params or {}))
                return [dict(record) for record in result]
        finally:
            drv.close()

    def set_tombstoned(self, path: str, timestamp: str) -> None:
        """Set tombstoned_at on the Artifact node matching the given path."""
        drv = self._driver()
        try:
            with drv.session() as session:
                session.run(
                    "MATCH (a:Artifact {path: $path}) SET a.tombstoned_at = $ts",
                    path=path, ts=timestamp,
                )
        finally:
            drv.close()

    def find_supersedes_source(self, old_path: str) -> dict | None:
        """If a `supersedes` edge points at the node for old_path, return
        {new_path, renamed_at}. Else None — either old_path was never renamed,
        or it was a pure deletion."""
        rows = self.query(
            "MATCH (new:Artifact)-[r:RELATES_TO {type: 'supersedes'}]->(old:Artifact {path: $path}) "
            "RETURN new.path AS new_path, r.attrs AS attrs LIMIT 1",
            {"path": old_path},
        )
        if not rows:
            return None
        try:
            attrs = json.loads(rows[0].get("attrs") or "{}")
        except Exception:
            attrs = {}
        return {"new_path": rows[0]["new_path"], "renamed_at": attrs.get("renamed_at", "")}

    def neighbors(self, node_id: str, depth: int = 1, scope: str | None = None) -> list[dict]:
        depth = max(1, min(depth, 4))
        conditions = ["(n.tombstoned_at IS NULL OR n.tombstoned_at = '')"]
        if scope:
            conditions.append("r.scope = $scope")
        where_clause = "WHERE " + " AND ".join(conditions)
        cypher = (
            f"MATCH (a:Artifact {{id: $id}})-[r:RELATES_TO*1..{depth}]-(n:Artifact) "
            f"{where_clause} "
            "RETURN DISTINCT n.id AS id, n.type AS type, n.path AS path, n.scope AS scope"
        )
        params: dict = {"id": node_id}
        if scope:
            params["scope"] = scope
        return self.query(cypher, params)

    def find_impact(
        self,
        node_id: str,
        depth: int = 4,
        edge_types: list[str] | None = None,
        project_ids: list[str] | None = None,
    ) -> list[dict]:
        """Phase 4: reverse traversal across the global graph — everything
        that transitively depends on node_id via the given edge types
        (default: calls, imports, extends), excluding tombstoned dependents.
        Answers "what breaks if I change this?" across promoted projects.
        Neo4j's Cypher binder has no issue with a list parameter inside
        ALL(...) over a variable-length path (unlike Kuzu's — see kg.py's
        impact() for the local-scope equivalent and its workaround).

        project_ids restricts which projects' dependents are returned
        (Phase 4 federated overlays: a project's own id plus any configured
        global_overlays). Every project promoted into this backend shares one
        physical Neo4j graph with no structural partitioning — without this
        filter, any project could see every other project's dependents with
        no isolation at all. Pass None only when you specifically want
        unrestricted cross-project results (e.g. an admin tool); kg_server.py's
        kg_impact tool always passes a concrete list for scope="global".
        """
        depth = max(1, min(depth, 6))
        types = edge_types or ["calls", "imports", "extends"]
        project_filter = "AND dependent.project_id IN $project_ids " if project_ids is not None else ""
        cypher = (
            f"MATCH p = (dependent:Artifact)-[r:RELATES_TO*1..{depth}]->(target:Artifact {{id: $node_id}}) "
            "WHERE ALL(rel IN r WHERE rel.type IN $edge_types) "
            "AND (dependent.tombstoned_at IS NULL OR dependent.tombstoned_at = '') "
            f"{project_filter}"
            "RETURN DISTINCT dependent.path AS path, dependent.project_id AS project_id, "
            "dependent.type AS type, length(p) AS distance "
            "ORDER BY distance"
        )
        params = {"node_id": node_id, "edge_types": types}
        if project_ids is not None:
            params["project_ids"] = project_ids
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

    def record_promotion(self, project_id: str, commit_sha: str, promoted_at: str, node_count: int, edge_count: int) -> None:
        """Phase 4: graph versioning — append-only promotion history.

        A separate PromotionRecord node type, not an Artifact property.
        registry.ProjectRecord.last_promoted_sha (Phase 3.3) is a single
        value overwritten on every promote, used as the rename-detection
        diff base — it is not a history and must not be conflated with this.
        counts reflect the total global graph size after this promotion
        completed (namespace_stats()), not this promotion's own delta.
        """
        drv = self._driver()
        try:
            with drv.session() as session:
                session.run(
                    "CREATE (p:PromotionRecord {project_id: $project_id, commit_sha: $commit_sha, "
                    "promoted_at: $promoted_at, node_count: $node_count, edge_count: $edge_count})",
                    project_id=project_id, commit_sha=commit_sha, promoted_at=promoted_at,
                    node_count=node_count, edge_count=edge_count,
                )
        finally:
            drv.close()

    def list_promotions(self, project_id: str) -> list[dict]:
        """Promotion history for a project, most recent first."""
        return self.query(
            "MATCH (p:PromotionRecord {project_id: $project_id}) "
            "RETURN p.commit_sha AS commit_sha, p.promoted_at AS promoted_at, "
            "p.node_count AS node_count, p.edge_count AS edge_count "
            "ORDER BY p.promoted_at DESC",
            {"project_id": project_id},
        )

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
