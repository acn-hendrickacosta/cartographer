"""Split extracted text into overlapping chunks suitable for embedding.

Chunking strategy (per DATA_MODEL.md):
  - Markdown/RST/docs: split on heading boundaries, then subdivide long sections
  - Code: split on top-level symbol boundaries (class/function/def), fall back to
    line-count windows
  - All chunks: max 512 tokens (~2000 chars). Overlap: 64 tokens (~256 chars).

Each chunk carries a stable symbol name if one was identified from the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cartographer.ingestion.text_extractor import ArtifactType

MAX_CHARS = 2000       # ~512 tokens at typical density
OVERLAP_CHARS = 256    # ~64 tokens overlap between successive chunks


@dataclass
class Chunk:
    ordinal: int
    text: str
    symbol: str | None  # top-level symbol this chunk came from, if identified
    spec_id: str | None  # spec identifier if this chunk belongs to a spec section


# --- Heading splitter (docs and specs) ---

_HEADING_RE = re.compile(r"^#{1,4}\s+.+$", re.MULTILINE)


def _split_on_headings(text: str) -> list[tuple[str | None, str]]:
    """Return list of (heading_text, section_body) pairs.

    The first element may have heading=None for any content before the first heading.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [(None, text)]

    sections: list[tuple[str | None, str]] = []
    pos = 0
    if matches[0].start() > 0:
        sections.append((None, text[: matches[0].start()].strip()))

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group().lstrip("#").strip()
        body = text[m.end() : end].strip()
        sections.append((heading, body))

    return [(h, b) for h, b in sections if b]


# --- Symbol splitter (code) ---

# Patterns that start a new top-level symbol for common languages
_SYMBOL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(async\s+)?def\s+\w+", re.MULTILINE),       # Python function
    re.compile(r"^class\s+\w+", re.MULTILINE),                  # Python/JS class
    re.compile(r"^function\s+\w+", re.MULTILINE),               # JS/TS function
    re.compile(r"^(export\s+)?(async\s+)?function\s+\w+", re.MULTILINE),
    re.compile(r"^(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(", re.MULTILINE),
    re.compile(r"^(pub\s+)?(async\s+)?fn\s+\w+", re.MULTILINE),  # Rust
    re.compile(r"^(public|private|protected|internal)\s+.*\(", re.MULTILINE),  # C#/Java
    re.compile(r"^func\s+\w+", re.MULTILINE),                   # Go
]


def _find_symbol_boundaries(text: str) -> list[tuple[str | None, int]]:
    """Return list of (symbol_name, char_offset) sorted by offset."""
    hits: list[tuple[int, str]] = []
    for pat in _SYMBOL_PATTERNS:
        for m in pat.finditer(text):
            # Only count truly top-level (no leading indent)
            line_start = text.rfind("\n", 0, m.start()) + 1
            indent = len(text[line_start : m.start()])
            if indent == 0:
                symbol = m.group().split("(")[0].split()[-1].strip()
                hits.append((m.start(), symbol))

    hits.sort(key=lambda h: h[0])
    # Deduplicate by offset
    seen: set[int] = set()
    unique: list[tuple[str | None, int]] = []
    for offset, symbol in hits:
        if offset not in seen:
            unique.append((symbol, offset))
            seen.add(offset)
    return unique


# --- Window splitter (fallback) ---

def _window_split(text: str, symbol: str | None = None) -> list[Chunk]:
    """Sliding-window split for long sections with no natural boundaries."""
    chunks: list[Chunk] = []
    ordinal = 0
    pos = 0
    while pos < len(text):
        end = min(pos + MAX_CHARS, len(text))
        chunk_text = text[pos:end].strip()
        if chunk_text:
            chunks.append(Chunk(ordinal=ordinal, text=chunk_text, symbol=symbol, spec_id=None))
            ordinal += 1
        pos = end - OVERLAP_CHARS
        if pos <= 0 or end == len(text):
            break
    return chunks


# --- Public API ---

def chunk_doc(text: str) -> list[Chunk]:
    """Chunk a documentation or spec file on heading boundaries."""
    sections = _split_on_headings(text)
    chunks: list[Chunk] = []
    ordinal = 0
    for heading, body in sections:
        if len(body) <= MAX_CHARS:
            if body:
                chunks.append(Chunk(ordinal=ordinal, text=body, symbol=heading, spec_id=None))
                ordinal += 1
        else:
            for sub in _window_split(body, symbol=heading):
                sub.ordinal = ordinal
                chunks.append(sub)
                ordinal += 1
    return chunks


def chunk_code(text: str) -> list[Chunk]:
    """Chunk a code file on top-level symbol boundaries."""
    boundaries = _find_symbol_boundaries(text)
    if not boundaries:
        return _window_split(text)

    chunks: list[Chunk] = []
    ordinal = 0
    prev_offset = 0
    prev_symbol: str | None = None

    for symbol, offset in boundaries:
        segment = text[prev_offset:offset].strip()
        if segment:
            for sub in _window_split(segment, symbol=prev_symbol):
                sub.ordinal = ordinal
                chunks.append(sub)
                ordinal += 1
        prev_offset = offset
        prev_symbol = symbol

    # Last segment
    segment = text[prev_offset:].strip()
    if segment:
        for sub in _window_split(segment, symbol=prev_symbol):
            sub.ordinal = ordinal
            chunks.append(sub)
            ordinal += 1

    return chunks


def chunk(text: str, artifact_type: ArtifactType) -> list[Chunk]:
    """Dispatch to the appropriate strategy based on artifact type."""
    if artifact_type in (ArtifactType.DOC, ArtifactType.SPEC):
        return chunk_doc(text)
    return chunk_code(text)
