# this_file: src/vexy_paraltext/cli.py
"""Command line: ``vexy-paraltext convert|normalize|embed|align|run|batch <book_dir>``."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import fire
from loguru import logger

from vexy_paraltext import pipeline
from vexy_paraltext.config import ModelSpec, load_config


def _log(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="{time:HH:mm:ss} {level:<7} {message}")


def _book(book_dir: str, config: str | None, verbose: bool) -> pipeline.Book:
    _log(verbose)
    path = Path(book_dir)
    return pipeline.Book(path, load_config(path, Path(config) if config else None))


def _embedding_options(book: pipeline.Book, model: str | None, backend: str | None, dimensions: int | None, precision: str | None) -> None:
    """Apply explicit CLI overrides to this invocation's loaded configuration."""
    if dimensions is not None:
        book.cfg.embed.dimensions = dimensions
    if precision is not None:
        book.cfg.embed.precision = precision
    if backend is not None:
        alias = model or book.cfg.embed.model
        spec = book.cfg.embed.models.get(alias, ModelSpec(model=alias))
        prefix = None if backend in {"jina", "voyage"} else spec.prefix
        book.cfg.embed.models[alias] = replace(spec, backend=backend, prefix=prefix)


class Cli:
    """vexy-paraltext: parallel sentences from multilingual book editions.

    Every command takes ``--config paraltext.toml`` (else the file is looked up in the book folder, cwd, ~/.config)
    and ``--verbose``. Stage outputs live in ``<book>/.paraltext/`` and are reused on the next call.
    """

    def convert(self, book_dir: str, config: str | None = None, force: bool = False, verbose: bool = False) -> str:
        """Stage 1: PDF/EPUB of every language folder -> ``.paraltext/<lang>.md``."""
        paths = pipeline.run_convert(_book(book_dir, config, verbose), force=force)
        return "\n".join(str(p) for p in paths)

    def normalize(self, book_dir: str, config: str | None = None, force: bool = False, verbose: bool = False) -> str:
        """Stage 2: LLM clean-up of the markdown -> ``.paraltext/<lang>.norm.md``."""
        paths = pipeline.run_normalize(_book(book_dir, config, verbose), force=force)
        return "\n".join(str(p) for p in paths)

    def embed(self, book_dir: str, model: str | None = None, limit: int | None = None, config: str | None = None, verbose: bool = False, backend: str | None = None, dimensions: int | None = None, precision: str | None = None) -> str:
        """Stage 3: sentence embeddings into the disk cache (``model``: alias from config or a GGUF path declared in config)."""
        book = _book(book_dir, config, verbose)
        _embedding_options(book, model, backend, dimensions, precision)
        eds = pipeline.run_embed(book, model=model, limit=limit)
        return "\n".join(f"{lang}: {len(ed.sentences)} sentences embedded" for lang, ed in eds.items())

    def align(
        self,
        book_dir: str,
        model: str | None = None,
        pivot: str | None = None,
        threshold: float | None = None,
        min_langs: int | None = None,
        limit: int | None = None,
        out: str | None = None,
        config: str | None = None,
        verbose: bool = False,
        backend: str | None = None,
        dimensions: int | None = None,
        precision: str | None = None,
    ) -> str:
        """Stage 4: mine parallel sentences and write ``<book_dir>/<book>.tmx``.

        Args:
            book_dir: folder with ``<lang>/<file>.pdf|epub`` subfolders.
            model: embedding model alias (config default: jina) or a GGUF path declared in config.
            pivot: source language (default ``en`` if present).
            threshold: margin-score cutoff; higher = fewer, cleaner pairs.
            min_langs: keep a unit when at least this many languages align (default: all).
            limit: first N sentences per language only (development).
            out: TMX path.
            config: path to paraltext.toml.
            verbose: debug logging.
        """
        book = _book(book_dir, config, verbose)
        _embedding_options(book, model, backend, dimensions, precision)
        res = pipeline.run_align(book, model=model, pivot=pivot, threshold=threshold, min_langs=min_langs, limit=limit, out=Path(out) if out else None)
        return f"{len(res.units)} units -> {res.tmx}"

    def run(
        self,
        book_dir: str,
        model: str | None = None,
        pivot: str | None = None,
        threshold: float | None = None,
        min_langs: int | None = None,
        limit: int | None = None,
        out: str | None = None,
        config: str | None = None,
        force: bool = False,
        verbose: bool = False,
        backend: str | None = None,
        dimensions: int | None = None,
        precision: str | None = None,
    ) -> str:
        """All stages: convert, normalize, embed, align (``force`` redoes convert and normalize)."""
        book = _book(book_dir, config, verbose)
        _embedding_options(book, model, backend, dimensions, precision)
        res = pipeline.run_all(
            book, force=force, model=model, pivot=pivot, threshold=threshold, min_langs=min_langs, limit=limit, out=Path(out) if out else None
        )
        return f"{len(res.units)} units -> {res.tmx}"

    def batch(self, root: str, config: str | None = None, verbose: bool = False) -> None:
        """``run`` on every book folder under ``root``; failures are logged, not fatal."""
        _log(verbose)
        for book in sorted(p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith(".")):
            try:
                print(self.run(str(book), config=config, verbose=verbose))
            except Exception as exc:  # noqa: BLE001
                logger.error("{}: {}", book.name, exc)


def main() -> None:
    """Entry point."""
    fire.Fire(Cli)
