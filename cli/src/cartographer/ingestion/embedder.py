"""Embed text chunks using the local fastembed model.

fastembed runs entirely on the developer's machine. No source code leaves the
machine for embedding. This is the only embedder supported in Phase 1.

If fastembed is not installed, embedding calls raise ImportError with an install hint
rather than silently producing empty vectors.
"""

from __future__ import annotations

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384  # matches lancedb driver DEFAULT_EMBEDDING_DIM


class Embedder:
    """Lazy-loaded local embedder backed by fastembed."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "fastembed is required for embedding. "
                    "Install it with: pip install \"cartographer-cli[embed]\""
                ) from exc
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text in `texts`."""
        if not texts:
            return []
        model = self._load()
        return [list(vec) for vec in model.embed(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM


_default_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Return the process-level default embedder (lazy-loaded on first call)."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder
