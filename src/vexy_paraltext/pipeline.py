# this_file: src/vexy_paraltext/pipeline.py
"""Book folder -> TMX in four cached stages: convert, normalize, embed, align."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from loguru import logger

from vexy_paraltext.align import Link, Span, align, with_bigrams
from vexy_paraltext.cache import EmbeddingCache, TextCache
from vexy_paraltext.config import Config
from vexy_paraltext.convert import SUFFIXES, ConvertError, convert, markdown_path, needs_ocr
from vexy_paraltext.embed import Embedder
from vexy_paraltext.normalize import normalize_file
from vexy_paraltext.segment import split_sentences
from vexy_paraltext.tmx import Unit, write_tmx


@dataclass
class Edition:
    """One language edition, segmented and embedded."""

    lang: str
    sentences: list[str]
    spans: list[Span] = field(default_factory=list)
    emb: np.ndarray | None = None

    def text(self, span: Span) -> str:
        return " ".join(self.sentences[i] for i in span)


@dataclass
class Result:
    """What ``run_align`` produced."""

    tmx: Path
    units: list[Unit]
    per_lang: dict[str, int]
    links: dict[str, list[Link]]


def is_multilingual_folder(name: str) -> bool:
    """``de-en`` (two or more 2-letter codes) is one volume in several languages; ``zh-hant`` is one language."""
    parts = name.split("-")
    return len(parts) > 1 and all(len(p) == 2 for p in parts)


@dataclass
class Book:
    """Paths for one book folder."""

    dir: Path
    cfg: Config

    @property
    def cache(self) -> Path:
        """Work folder for diskcache and converter scratch (not hidden: ``<book>/paraltext-cache``)."""
        return self.dir / self.cfg.cache_dir

    def editions(self) -> list[Path]:
        """Single-language edition folders (``de-en`` style multilingual volumes are skipped)."""
        out = []
        for d in sorted(p for p in self.dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if is_multilingual_folder(d.name):
                logger.warning("skipping multilingual volume {}", d.name)
                continue
            if any(f.suffix.lower() in SUFFIXES for f in d.iterdir()):
                out.append(d)
        if len(out) < 2:
            msg = f"need at least two language editions in {self.dir}"
            raise ValueError(msg)
        return out

    def langs(self) -> list[str]:
        return [d.name for d in self.editions()]

    def converted_langs(self) -> list[str]:
        """Editions whose (normalized) markdown exists; the others were unconvertible and are skipped."""
        out = [lang for lang in self.langs() if self.norm_md(lang).exists()]
        if len(out) < 2:
            msg = f"fewer than two converted editions in {self.dir}: run convert first"
            raise ValueError(msg)
        return out

    def raw_md(self, lang: str) -> Path:
        """``<lang>/<stem>.md`` next to the source."""
        return markdown_path(self.dir / lang)

    def norm_md(self, lang: str) -> Path:
        """``<lang>/<stem>.norm.md`` next to the source (or the raw markdown when normalize is off)."""
        raw = self.raw_md(lang)
        return raw.with_suffix(".norm.md") if self.cfg.normalize.enabled else raw


def run_convert(book: Book, *, force: bool = False) -> list[Path]:
    """Stage 1: every edition to ``.paraltext/<lang>.md``.

    Text-layer PDFs and EPUBs convert in parallel; scanned PDFs (docling OCR) run one at a time,
    because several OCR pipelines side by side exhaust memory.
    """
    dirs = book.editions()
    scans = [d for d in dirs if needs_ocr(d)]
    fast = [d for d in dirs if d not in scans]

    def one(d: Path) -> Path | None:
        try:
            return convert(d, book.cache, force=force, epub2md=book.cfg.convert.epub2md)
        except ConvertError as exc:
            logger.error("{}/{}: {}", book.dir.name, d.name, exc)
            return None

    with ThreadPoolExecutor(max(1, book.cfg.convert.workers)) as ex:
        done = dict(zip(fast, ex.map(one, fast), strict=True))
    done.update({d: one(d) for d in scans})
    return [p for d in dirs if (p := done[d]) is not None]


def run_normalize(book: Book, *, force: bool = False) -> list[Path]:
    """Stage 2: LLM clean-up to ``.paraltext/<lang>.norm.md`` (chunks in parallel, cached)."""
    if not book.cfg.normalize.enabled:
        logger.info("normalize disabled in config, using raw markdown")
        return [book.raw_md(lang) for lang in book.langs()]
    cache = TextCache(book.cache / "cache")
    try:
        return [
            normalize_file(book.raw_md(lang), book.norm_md(lang), book.cfg.normalize, cache, force=force) for lang in book.langs() if book.raw_md(lang).exists()
        ]
    finally:
        cache.close()


def load_edition(book: Book, lang: str, *, limit: int | None = None) -> Edition:
    """Segment the (normalized) markdown of one edition."""
    md = book.norm_md(lang)
    if not md.exists():
        msg = f"{md} missing: run convert/normalize first"
        raise FileNotFoundError(msg)
    sentences = split_sentences(md.read_text(encoding="utf-8"), lang)
    if limit:
        sentences = sentences[:limit]
    logger.info("{}: {} sentences", lang, len(sentences))
    return Edition(lang, sentences)


def run_embed(book: Book, *, model: str | None = None, limit: int | None = None) -> dict[str, Edition]:
    """Stage 3: embed sentences and adjacent pairs of every edition into the disk cache."""
    embedder = Embedder.from_alias(model or book.cfg.embed.model, book.cfg.embed.models)
    cache = EmbeddingCache(book.cache / "cache")
    try:
        eds = {}
        for lang in book.converted_langs():
            ed = load_edition(book, lang, limit=limit)
            texts, ed.spans = with_bigrams(ed.sentences)
            ed.emb = embedder.embed_cached(texts, cache)
            eds[lang] = ed
        return eds
    finally:
        cache.close()


def run_align(
    book: Book,
    eds: dict[str, Edition] | None = None,
    *,
    model: str | None = None,
    pivot: str | None = None,
    threshold: float | None = None,
    min_langs: int | None = None,
    limit: int | None = None,
    out: Path | None = None,
) -> Result:
    """Stage 4: mine parallel sentences against the pivot language and write the TMX."""
    eds = eds or run_embed(book, model=model, limit=limit)
    cfg = book.cfg
    pivot = pivot or cfg.pivot or ("en" if "en" in eds else next(iter(eds)))
    threshold = cfg.embed.threshold if threshold is None else threshold
    src = eds[pivot]
    assert src.emb is not None
    targets = [ed for lang, ed in eds.items() if lang != pivot]

    def one(ed: Edition) -> list[Link]:
        assert ed.emb is not None
        assert src.emb is not None
        links = align(src.spans, src.emb, ed.spans, ed.emb, threshold=threshold, gap_min_cos=cfg.embed.gap_min_cos, center_vectors=cfg.embed.center)
        logger.info("{} -> {}: {} links", pivot, ed.lang, len(links))
        return links

    with ThreadPoolExecutor(max(1, len(targets))) as ex:
        links = dict(zip([ed.lang for ed in targets], ex.map(one, targets), strict=True))
    matches = {
        lang: {lk.src: eds[lang].text(lk.tgt) for lk in lks if not is_untranslated(src.text(lk.src), eds[lang].text(lk.tgt))} for lang, lks in links.items()
    }
    need = max(1, (min_langs or cfg.min_langs) - 1)  # editions besides the pivot
    units: list[Unit] = []
    for span in sorted({s for m in matches.values() for s in m}):
        hits = {lang: m[span] for lang, m in matches.items() if span in m}
        if len(hits) >= need:
            units.append({pivot: src.text(span), **hits})
    tmx = out or book.dir / f"{book.dir.name}.tmx"
    write_tmx(units, tmx, srclang=pivot)
    logger.info("wrote {} units to {}", len(units), tmx)
    return Result(tmx, units, {k: len(v.sentences) for k, v in eds.items()}, links)


def is_untranslated(a: str, b: str) -> bool:
    """True when the "translation" is the source text itself (bilingual editions quote the original)."""
    norm = str.maketrans("", "", " \t\n\u2019'\"\u201c\u201d.,;:!?-\u2013\u2014()")
    return a.translate(norm).casefold() == b.translate(norm).casefold()


def run_all(
    book: Book,
    *,
    force: bool = False,
    model: str | None = None,
    pivot: str | None = None,
    threshold: float | None = None,
    min_langs: int | None = None,
    limit: int | None = None,
    out: Path | None = None,
) -> Result:
    """All four stages in order."""
    run_convert(book, force=force)
    run_normalize(book, force=force)
    return run_align(book, model=model, pivot=pivot, threshold=threshold, min_langs=min_langs, limit=limit, out=out)
