# this_file: src/vexy_paraltext/cache.py
"""diskcache-backed stores: one for LLM-normalized chunks, one for sentence embeddings."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from diskcache import Cache


def _key(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode()).hexdigest()  # noqa: S324


class TextCache:
    """String -> string (normalized chunk) keyed by model, prompt version and input."""

    def __init__(self, directory: Path) -> None:
        self.cache = Cache(str(directory / "normalize"), size_limit=2**31)

    def get(self, model: str, version: str, text: str) -> str | None:
        return self.cache.get(_key(model, version, text))

    def put(self, model: str, version: str, text: str, out: str) -> None:
        self.cache.set(_key(model, version, text), out)

    def close(self) -> None:
        self.cache.close()


class EmbeddingCache:
    """Per-sentence float32 vectors keyed by model name and text."""

    def __init__(self, directory: Path) -> None:
        self.cache = Cache(str(directory / "embeddings"), size_limit=2**33)

    def lookup(self, model: str, texts: list[str]) -> tuple[list[np.ndarray | None], list[int]]:
        """Vectors for known texts (None otherwise) and the indices still missing."""
        found: list[np.ndarray | None] = []
        missing: list[int] = []
        for i, t in enumerate(texts):
            blob = self.cache.get(_key(model, t))
            if blob is None:
                found.append(None)
                missing.append(i)
            else:
                found.append(np.frombuffer(blob, dtype=np.float32))
        return found, missing

    def store(self, model: str, texts: list[str], vectors: np.ndarray) -> None:
        with self.cache.transact():
            for t, v in zip(texts, vectors, strict=True):
                self.cache.set(_key(model, t), np.ascontiguousarray(v, dtype=np.float32).tobytes())

    def close(self) -> None:
        self.cache.close()
