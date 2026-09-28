"""Unit tests for the ingestion chunker."""

import pytest

from cartographer.ingestion import chunker
from cartographer.ingestion.text_extractor import ArtifactType


def test_chunk_doc_empty():
    assert chunker.chunk("", ArtifactType.DOC) == []


def test_chunk_doc_no_headings():
    text = "A simple doc with no headings.\nJust some text."
    chunks = chunker.chunk(text, ArtifactType.DOC)
    assert len(chunks) == 1
    assert chunks[0].text == text.strip()
    assert chunks[0].symbol is None


def test_chunk_doc_headings():
    text = "# Overview\nThis is the overview.\n\n## Details\nThis is the detail."
    chunks = chunker.chunk(text, ArtifactType.DOC)
    assert len(chunks) == 2
    assert chunks[0].symbol == "Overview"
    assert chunks[1].symbol == "Details"
    assert "overview" in chunks[0].text.lower()
    assert "detail" in chunks[1].text.lower()


def test_chunk_doc_long_section_splits():
    body = "word " * 600  # > MAX_CHARS of 2000 chars
    text = "# Big section\n" + body
    chunks = chunker.chunk(text, ArtifactType.DOC)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= chunker.MAX_CHARS


def test_chunk_code_empty():
    assert chunker.chunk("", ArtifactType.CODE) == []


def test_chunk_code_symbols():
    code = "def foo():\n    pass\n\ndef bar():\n    return 1\n"
    chunks = chunker.chunk(code, ArtifactType.CODE)
    symbols = {c.symbol for c in chunks}
    assert "foo" in symbols or "bar" in symbols


def test_chunk_code_no_symbols_falls_back_to_window():
    code = "x = 1\ny = 2\nz = 3\n"
    chunks = chunker.chunk(code, ArtifactType.CODE)
    # Should return at least one chunk
    assert len(chunks) >= 1
    assert chunks[0].text.strip()


def test_chunk_spec_uses_doc_strategy():
    text = "# Requirements\nMust do X.\n\n# Non-Goals\nNot Y."
    chunks = chunker.chunk(text, ArtifactType.SPEC)
    assert len(chunks) == 2
    assert chunks[0].symbol == "Requirements"


def test_chunk_ordinals_are_sequential():
    code = "\n\n".join(f"def func_{i}():\n    pass" for i in range(5))
    chunks = chunker.chunk(code, ArtifactType.CODE)
    for i, c in enumerate(chunks):
        assert c.ordinal == i
