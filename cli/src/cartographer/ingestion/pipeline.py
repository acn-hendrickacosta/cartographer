"""Ingestion pipeline: orchestrate extraction, chunking, embedding, and upsert.

Accepts a list of file paths (or a root directory), processes them, and writes
chunks and graph nodes/edges into the local VDB and KG.

Returns an IngestionResult summary that callers (seed command, flush hook) use
to report what happened.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from cartographer.artifact_id import chunk_id as make_chunk_id
from cartographer.ingestion import chunker, graph_extractor, text_extractor
from cartographer.ingestion.embedder import Embedder, get_embedder
from cartographer.indexing import kg as kg_driver
from cartographer.indexing import vdb as vdb_driver
from cartographer.indexing.vdb import ChunkRecord


@dataclass
class IngestionResult:
    files_processed: int = 0
    files_skipped: int = 0
    chunks_upserted: int = 0
    nodes_upserted: int = 0
    edges_upserted: int = 0
    skipped_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def ingest_paths(
    paths: list[Path],
    *,
    project_id: str,
    workspace_root: Path,
    vdb_path: Path,
    kg_path: Path,
    scope: str = "local",
    embedder: Embedder | None = None,
) -> IngestionResult:
    """Ingest a list of files into the local VDB and KG.

    Idempotent: VDB upserts are keyed on chunk_id; KG upserts are keyed on node id.
    """
    if embedder is None:
        embedder = get_embedder()

    result = IngestionResult()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Ensure backends are ready
    vdb_driver.ensure_collection(vdb_path, scope=scope, embedding_dim=embedder.dim)
    kg_driver.ensure_namespace(kg_path)

    for path in paths:
        extraction = text_extractor.extract(path)
        if extraction.skipped:
            result.files_skipped += 1
            result.skipped_paths.append(f"{path}: {extraction.skip_reason}")
            continue

        try:
            _ingest_one(
                extraction=extraction,
                project_id=project_id,
                workspace_root=workspace_root,
                vdb_path=vdb_path,
                kg_path=kg_path,
                scope=scope,
                embedder=embedder,
                now=now,
                result=result,
            )
            result.files_processed += 1
        except Exception as exc:
            result.errors.append(f"{path}: {exc}")

    return result


def _ingest_one(
    extraction: text_extractor.ExtractionResult,
    project_id: str,
    workspace_root: Path,
    vdb_path: Path,
    kg_path: Path,
    scope: str,
    embedder: Embedder,
    now: str,
    result: IngestionResult,
) -> None:
    rel_path = str(extraction.path.relative_to(workspace_root))
    artifact_type = extraction.artifact_type
    text = extraction.text

    # 1. Chunk
    chunks = chunker.chunk(text, artifact_type)
    if not chunks:
        return

    # 2. Embed
    texts = [c.text for c in chunks]
    embeddings = embedder.embed(texts)

    # 3. Build VDB records
    records: list[ChunkRecord] = []
    for chunk, embedding in zip(chunks, embeddings):
        cid = make_chunk_id(rel_path, chunk.ordinal, chunk.symbol)
        records.append(
            ChunkRecord(
                id=cid,
                project_id=project_id,
                scope=scope,
                artifact_type=artifact_type.value,
                path=rel_path,
                symbol=chunk.symbol,
                spec_id=chunk.spec_id,
                origin=scope,
                text=chunk.text,
                embedding=embedding,
                updated_at=now,
            )
        )

    # 4. Upsert VDB
    upserted = vdb_driver.upsert(vdb_path, scope=scope, chunks=records, embedding_dim=embedder.dim)
    result.chunks_upserted += upserted

    # 5. Extract KG graph
    graph = graph_extractor.extract(
        path=extraction.path,
        text=text,
        artifact_type=artifact_type,
        project_id=project_id,
        scope=scope,
        workspace_root=workspace_root,
    )

    # 6. Upsert KG
    kg_driver.upsert_nodes(kg_path, graph.nodes)
    kg_driver.upsert_edges(kg_path, graph.edges)
    result.nodes_upserted += len(graph.nodes)
    result.edges_upserted += len(graph.edges)


def ingest_directory(
    root: Path,
    *,
    project_id: str,
    workspace_root: Path,
    vdb_path: Path,
    kg_path: Path,
    scope: str = "local",
    embedder: Embedder | None = None,
    recursive: bool = True,
) -> IngestionResult:
    """Ingest all ingestable files under `root`."""
    paths = text_extractor.collect_paths(root, recursive=recursive)
    return ingest_paths(
        paths,
        project_id=project_id,
        workspace_root=workspace_root,
        vdb_path=vdb_path,
        kg_path=kg_path,
        scope=scope,
        embedder=embedder,
    )
