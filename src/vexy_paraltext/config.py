# this_file: src/vexy_paraltext/config.py
"""TOML configuration: ``paraltext.toml`` in the book folder, the cwd, or ``~/.config/vexy-paraltext/``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from loguru import logger

CONFIG_NAME = "paraltext.toml"
_LMS = "/Volumes/Falstaff4T/RomeoData2/lmstudio/models"


@dataclass
class ModelSpec:
    path: str
    prefix: str = ""


@dataclass
class EmbedConfig:
    model: str = "jina"
    threshold: float = 1.05
    gap_min_cos: float = 0.6
    center: bool = True  # subtract the mean vector before mining (removes anisotropy; scale-free margins)
    models: dict[str, ModelSpec] = field(
        default_factory=lambda: {
            "jina": ModelSpec(f"{_LMS}/jinaai/jina-embeddings-v5-text-nano-text-matching/v5-nano-text-matching-Q8_0.gguf", "Query: "),
            "gemma": ModelSpec(f"{_LMS}/mntcloud/embeddinggemma-300m-Q8_0-better-gguf/embeddinggemma-300M-Q8_0.gguf", "task: sentence similarity | query: "),
            "granite": ModelSpec(f"{_LMS}/mykor/granite-embedding-311m-multilingual-r2-GGUF/granite-embedding-311M-multilingual-r2-Q8_0.gguf", ""),
        }
    )


@dataclass
class NormalizeConfig:
    enabled: bool = True
    model: str = "gemma-4-26b-a4b-it-qat-mxfp8"
    base_url: str = "http://localhost:1234/v1"
    workers: int = 4
    chunk_chars: int = 3000
    max_tokens: int = 2500
    temperature: float = 0.1
    timeout: float = 1800.0


@dataclass
class ConvertConfig:
    epub2md: str = "~/bin/epub2md.py"
    workers: int = 3


@dataclass
class Config:
    embed: EmbedConfig = field(default_factory=EmbedConfig)
    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    convert: ConvertConfig = field(default_factory=ConvertConfig)
    pivot: str | None = None
    min_langs: int = 2  # a unit is kept when the pivot sentence aligns in at least this many editions (pivot included)
    cache_dir: str = "paraltext-cache"


def _merge(obj: Any, data: dict[str, Any]) -> Any:
    for f in fields(obj):
        if f.name not in data:
            continue
        val = data[f.name]
        cur = getattr(obj, f.name)
        if is_dataclass(cur) and isinstance(val, dict):
            _merge(cur, val)
        elif f.name == "models" and isinstance(val, dict):
            cur.update({k: ModelSpec(**v) for k, v in val.items()})
        else:
            setattr(obj, f.name, val)
    return obj


def candidate_paths(book_dir: Path | None) -> list[Path]:
    paths = [Path(book_dir) / CONFIG_NAME] if book_dir else []
    return [*paths, Path.cwd() / CONFIG_NAME, Path.home() / ".config" / "vexy-paraltext" / CONFIG_NAME]


def load_config(book_dir: Path | None = None, explicit: Path | None = None) -> Config:
    """Defaults, overlaid with the first config file found (or ``explicit``)."""
    cfg = Config()
    for path in [explicit] if explicit else candidate_paths(book_dir):
        if path and path.exists():
            logger.debug("config {}", path)
            _merge(cfg, tomllib.loads(path.read_text(encoding="utf-8")))
            break
    return cfg
