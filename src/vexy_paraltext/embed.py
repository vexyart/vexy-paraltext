# this_file: src/vexy_paraltext/embed.py
"""Sentence alignment adapter for the shared uubed embedding system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loguru import logger
from uubed.embeddings import Embedder as SharedEmbedder

from vexy_paraltext.cache import EmbeddingCache
from vexy_paraltext.config import EmbedConfig, ModelSpec

MODELS: dict[str, tuple[Path, str | None]] = {k: (Path(v.path), v.prefix) for k, v in EmbedConfig().models.items()}


@dataclass
class Embedder:
    """Keep alignment orchestration separate from shared inference and quantization."""

    name: str
    path: Path
    prefix: str | None
    options: EmbedConfig | None = None
    spec: ModelSpec | None = None
    _engine: SharedEmbedder | None = None

    @classmethod
    def from_alias(cls, alias: str, models: dict[str, ModelSpec] | None = None, options: EmbedConfig | None = None) -> Embedder:
        specs = models or EmbedConfig().models
        if alias in specs:
            spec = specs[alias]
            return cls(alias, Path(spec.path).expanduser(), spec.prefix, options, spec)
        path = Path(alias).expanduser()
        for name, spec in specs.items():
            if spec.path and Path(spec.path).expanduser().resolve() == path.resolve():
                return cls(name, path, spec.prefix, options, spec)
        if not path.is_file():
            msg = f"unknown model alias or missing GGUF: {alias}"
            raise FileNotFoundError(msg)
        msg = "GGUF requires a model profile: set [embed.models.<alias>] path and model (e.g. jina or gemma)"
        raise ValueError(msg)

    def _shared(self) -> SharedEmbedder:
        if self._engine is None:
            config = self.options or EmbedConfig()
            spec = self.spec or ModelSpec(str(self.path), self.prefix)
            if spec.backend == "llama.cpp" and not self.path.is_file():
                msg = f"model file missing: {self.path}"
                raise FileNotFoundError(msg)
            self._engine = SharedEmbedder(
                spec.model or self.name,
                backend=spec.backend,
                path=self.path if spec.backend == "llama.cpp" else None,
                device=spec.device,
                prefix=self.prefix,
                dimensions=config.dimensions,
                precision=config.precision,
                max_tokens=config.max_tokens,
                batch_tokens=config.batch_tokens,
                batch_size=config.batch_size,
                endpoint=spec.endpoint,
            )
        return self._engine

    @property
    def cache_identity(self) -> str:
        return self._shared().cache_identity

    def embed(self, texts: list[str]) -> np.ndarray:
        """Infer normalized vectors through the same engine as other uubed consumers."""
        return self._shared().embed(texts)

    def embed_cached(self, texts: list[str], cache: EmbeddingCache) -> np.ndarray:
        """Quantized per-sentence storage; cold and warm reads return identical vectors."""
        identity = self.cache_identity
        found, missing = cache.lookup(identity, texts)
        if missing:
            logger.info("embedding {} new texts with {} ({} cached)", len(missing), self.name, len(texts) - len(missing))
            fresh = self.embed([texts[i] for i in missing])
            cache.store(identity, [texts[i] for i in missing], fresh, precision=(self.options or EmbedConfig()).precision)
            found, missing = cache.lookup(identity, texts)
            if missing:
                msg = "embedding cache failed to retain freshly stored vectors"
                raise RuntimeError(msg)
        vectors = [v for v in found if v is not None]
        return np.vstack(vectors) if vectors else np.empty((0, (self.options or EmbedConfig()).dimensions or 0), dtype=np.float32)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
