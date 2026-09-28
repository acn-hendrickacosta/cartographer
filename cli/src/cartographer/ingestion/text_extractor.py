"""Extract plain text from files that Cartographer can ingest.

Supported formats (Phase 1):
  - Plain text: .md, .rst, .txt, .adoc, .py, .ts, .tsx, .js, .jsx, .go, .rs,
    .java, .kt, .swift, .c, .cpp, .h, .hpp, .cs, .rb, .php, .sh, .yaml, .yml,
    .json, .toml, .ini, .conf, .html, .css, .scss, .sql

Binary formats (.docx, .pptx, .pdf) require a Claude Code session for extraction
and are skipped with a warning when run outside one.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


class ArtifactType(str, Enum):
    CODE = "code"
    DOC = "doc"
    SPEC = "spec"


# Extensions that map to a plain-text read
_PLAIN_TEXT_EXTENSIONS: dict[str, ArtifactType] = {
    ".md": ArtifactType.DOC,
    ".rst": ArtifactType.DOC,
    ".txt": ArtifactType.DOC,
    ".adoc": ArtifactType.DOC,
    ".py": ArtifactType.CODE,
    ".ts": ArtifactType.CODE,
    ".tsx": ArtifactType.CODE,
    ".js": ArtifactType.CODE,
    ".jsx": ArtifactType.CODE,
    ".go": ArtifactType.CODE,
    ".rs": ArtifactType.CODE,
    ".java": ArtifactType.CODE,
    ".kt": ArtifactType.CODE,
    ".swift": ArtifactType.CODE,
    ".c": ArtifactType.CODE,
    ".cpp": ArtifactType.CODE,
    ".h": ArtifactType.CODE,
    ".hpp": ArtifactType.CODE,
    ".cs": ArtifactType.CODE,
    ".rb": ArtifactType.CODE,
    ".php": ArtifactType.CODE,
    ".sh": ArtifactType.CODE,
    ".yaml": ArtifactType.CODE,
    ".yml": ArtifactType.CODE,
    ".json": ArtifactType.CODE,
    ".toml": ArtifactType.CODE,
    ".ini": ArtifactType.CODE,
    ".conf": ArtifactType.CODE,
    ".html": ArtifactType.CODE,
    ".css": ArtifactType.CODE,
    ".scss": ArtifactType.CODE,
    ".sql": ArtifactType.CODE,
}

# Spec files are detected by name pattern regardless of extension
_SPEC_NAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"SPEC", re.IGNORECASE),
    re.compile(r"\.spec\.", re.IGNORECASE),
    re.compile(r"RFC", re.IGNORECASE),
    re.compile(r"ADR[-_]\d+", re.IGNORECASE),
    re.compile(r"DESIGN", re.IGNORECASE),
    re.compile(r"REQUIREMENTS?", re.IGNORECASE),
    re.compile(r"PRD[-_\.]", re.IGNORECASE),
]

# Binary formats skipped with a warning outside Claude Code
_BINARY_EXTENSIONS = {".docx", ".pptx", ".pdf"}


class ExtractionResult:
    __slots__ = ("path", "text", "artifact_type", "skipped", "skip_reason")

    def __init__(
        self,
        path: Path,
        text: str,
        artifact_type: ArtifactType,
        skipped: bool = False,
        skip_reason: str = "",
    ) -> None:
        self.path = path
        self.text = text
        self.artifact_type = artifact_type
        self.skipped = skipped
        self.skip_reason = skip_reason


def _is_spec(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in _SPEC_NAME_PATTERNS)


def _artifact_type_for(path: Path) -> ArtifactType:
    base = _PLAIN_TEXT_EXTENSIONS.get(path.suffix.lower(), ArtifactType.CODE)
    if base == ArtifactType.DOC and _is_spec(path):
        return ArtifactType.SPEC
    if base == ArtifactType.CODE and _is_spec(path):
        return ArtifactType.SPEC
    return base


def extract(path: Path) -> ExtractionResult:
    """Read text from a file and classify it as code, doc, or spec.

    Returns a skipped result for binary formats and unreadable files.
    """
    suffix = path.suffix.lower()

    if suffix in _BINARY_EXTENSIONS:
        return ExtractionResult(
            path=path,
            text="",
            artifact_type=ArtifactType.DOC,
            skipped=True,
            skip_reason=(
                f"Binary format {suffix!r} requires a Claude Code session for extraction. "
                "Run `cartographer seed` from within a Claude Code session to ingest this file."
            ),
        )

    if suffix not in _PLAIN_TEXT_EXTENSIONS:
        return ExtractionResult(
            path=path,
            text="",
            artifact_type=ArtifactType.CODE,
            skipped=True,
            skip_reason=f"Unsupported extension {suffix!r}",
        )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ExtractionResult(
            path=path,
            text="",
            artifact_type=ArtifactType.CODE,
            skipped=True,
            skip_reason=str(exc),
        )

    artifact_type = _artifact_type_for(path)
    return ExtractionResult(path=path, text=text, artifact_type=artifact_type)


def collect_paths(root: Path, recursive: bool = True) -> list[Path]:
    """Return all ingestable file paths under `root`.

    Skips hidden directories and common ignore patterns (.git, __pycache__, node_modules, .venv).
    """
    ignored_dirs = {".git", "__pycache__", "node_modules", ".venv", ".env", ".tox", "dist", "build"}
    paths: list[Path] = []

    if root.is_file():
        return [root]

    glob = root.rglob("*") if recursive else root.glob("*")
    for p in glob:
        if not p.is_file():
            continue
        if any(part in ignored_dirs for part in p.parts):
            continue
        if p.name.startswith("."):
            continue
        suffix = p.suffix.lower()
        if suffix in _PLAIN_TEXT_EXTENSIONS or suffix in _BINARY_EXTENSIONS:
            paths.append(p)

    return sorted(paths)
