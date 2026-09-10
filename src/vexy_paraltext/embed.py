# this_file: src/vexy_paraltext/embed.py
"""Sentence embeddings from local GGUF models via llama.cpp, cached as .npz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from vexy_paraltext.cache import EmbeddingCache
from vexy_paraltext.config import EmbedConfig, ModelSpec

MODELS: dict[str, tuple[Path, str]] = {k: (Path(v.path), v.prefix) for k, v in EmbedConfig().models.items()}
MAX_TOKENS = 512  # per text
BATCH_TOKENS = 4096  # per llama.cpp call


@dataclass
class Embedder:
    """Lazy wrapper around a llama.cpp embedding model."""

    name: str
    path: Path
    prefix: str
    _llm: Any = None

    @classmethod
    def from_alias(cls, alias: str, models: dict[str, ModelSpec] | None = None) -> Embedder:
        """Resolve a configured alias (``jina``/``gemma``) or a raw GGUF path (prefix empty for raw paths)."""
        specs = {k: (Path(v.path), v.prefix) for k, v in models.items()} if models else MODELS
        if alias in specs:
            path, prefix = specs[alias]
            return cls(alias, path, prefix)
        path = Path(alias).expanduser()
        return cls(path.stem, path, "")

    def _model(self) -> Any:
        if self._llm is None:
            if not self.path.exists():
                msg = f"model file missing: {self.path}"
                raise FileNotFoundError(msg)
            from llama_cpp import Llama  # noqa: PLC0415

            logger.info("loading {}", self.path.name)
            self._llm = Llama(
                model_path=str(self.path), embedding=True, n_gpu_layers=-1, n_ctx=BATCH_TOKENS, n_batch=BATCH_TOKENS, n_ubatch=BATCH_TOKENS, verbose=False
            )
        return self._llm

    def embed(self, texts: list[str]) -> np.ndarray:
        """L2-normalised float32 embeddings, one row per text."""
        llm = self._model()
        rows: list[list[float]] = []
        batch: list[str] = []
        used = 0
        for text in texts:
            toks = llm.tokenize((self.prefix + text).encode(), add_bos=False, special=False)
            clipped = llm.detokenize(toks[:MAX_TOKENS]).decode(errors="ignore")
            n = min(len(toks), MAX_TOKENS) + 2
            if batch and used + n > BATCH_TOKENS:
                rows.extend(llm.embed(batch))
                batch, used = [], 0
            batch.append(clipped)
            used += n
        if batch:
            rows.extend(llm.embed(batch))
        arr = np.asarray(rows, dtype=np.float32)
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        return arr

    def embed_cached(self, texts: list[str], cache: EmbeddingCache) -> np.ndarray:
        """Embed with a per-sentence disk cache; only unseen texts hit the model."""
        found, missing = cache.lookup(self.name, texts)
        if missing:
            logger.info("embedding {} new texts with {} ({} cached)", len(missing), self.name, len(texts) - len(missing))
            fresh = self.embed([texts[i] for i in missing])
            cache.store(self.name, [texts[i] for i in missing], fresh)
            for i, v in zip(missing, fresh, strict=True):
                found[i] = v
        vectors: list[np.ndarray] = [v for v in found if v is not None]
        return np.vstack(vectors) if vectors else np.zeros((0, 1), dtype=np.float32)
