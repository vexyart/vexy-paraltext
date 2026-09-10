# this_file: src/vexy_paraltext/normalize.py
"""LLM pass that turns converter markdown into plain paragraphs of plain sentences.

Runs against an OpenAI-compatible server (LM Studio by default), chunk by chunk, in parallel, with a disk cache.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from loguru import logger

from vexy_paraltext.cache import TextCache
from vexy_paraltext.config import NormalizeConfig

PROMPT_VERSION = "v1"
RETRIES = 3
MAX_SPLIT_DEPTH = 3
SYSTEM_PROMPT = (
    "You normalize text extracted from a PDF or EPUB book for a translation memory. "
    "Output plain paragraphs of complete sentences, blank line between paragraphs. "
    "Rules: fix broken words and stray spaces inside words (e.g. 'AD R I A N' -> 'Adrian', 'sa me' -> 'same'); "
    "use standard sentence case, never ALL CAPS or letter-spaced words; keep correct punctuation; "
    "keep every sentence and its meaning, do not summarize, do not translate, do not add commentary; "
    "drop page numbers, running heads, tables of contents, figure numbers like /01/, footnote markers and all markdown syntax; "
    "keep captions as normal sentences. Answer in the language of the input with the normalized text only."
)
_BLANK = re.compile(r"\n\s*\n")


def chunk_markdown(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most ``max_chars`` (long paragraphs are cut)."""
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for raw in _BLANK.split(text):
        para = raw.strip()
        if not para:
            continue
        while len(para) > max_chars:
            if cur:
                chunks.append("\n\n".join(cur))
                cur, size = [], 0
            cut = para.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            chunks.append(para[:cut])
            para = para[cut:].strip()
        if size + len(para) + 2 > max_chars and cur:
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(para)
        size += len(para) + 2
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


class Normalizer:
    """Chat-completion client with a per-chunk cache."""

    def __init__(self, cfg: NormalizeConfig, cache: TextCache) -> None:
        self.cfg = cfg
        self.cache = cache
        self.client = httpx.Client(base_url=cfg.base_url, timeout=cfg.timeout)

    def _request(self, chunk: str) -> tuple[str, str]:
        body = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": chunk}],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                resp = self.client.post("/chat/completions", json=body)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                return choice["message"]["content"].strip(), choice.get("finish_reason", "stop")
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
                logger.warning("normalize request failed ({}), retry {}/{}", exc, attempt + 1, RETRIES)
                time.sleep(2**attempt)
        msg = f"normalize failed after {RETRIES} attempts: {last}"
        raise RuntimeError(msg)

    def complete(self, chunk: str, depth: int = 0) -> str:
        """Normalize one chunk; a truncated answer splits the chunk in half and retries."""
        cached = self.cache.get(self.cfg.model, PROMPT_VERSION, chunk)
        if cached is not None:
            return cached
        out, finish = self._request(chunk)
        if finish == "length" and depth < MAX_SPLIT_DEPTH:
            cut = chunk.rfind("\n\n", 0, len(chunk) // 2 + 200)
            cut = cut if cut > 0 else len(chunk) // 2
            logger.warning("answer truncated, splitting chunk of {} chars", len(chunk))
            out = self.complete(chunk[:cut], depth + 1) + "\n\n" + self.complete(chunk[cut:].lstrip(), depth + 1)
        self.cache.put(self.cfg.model, PROMPT_VERSION, chunk, out)
        return out

    def normalize(self, text: str) -> str:
        chunks = chunk_markdown(text, self.cfg.chunk_chars)
        logger.info("normalizing {} chunks with {} ({} workers)", len(chunks), self.cfg.model, self.cfg.workers)
        with ThreadPoolExecutor(self.cfg.workers) as ex:
            parts = list(ex.map(self.complete, chunks))
        return "\n\n".join(parts) + "\n"


def normalize_file(src: Path, dst: Path, cfg: NormalizeConfig, cache: TextCache, *, force: bool = False) -> Path:
    """``<lang>.md`` -> ``<lang>.norm.md`` (skipped when present unless ``force``)."""
    if dst.exists() and not force:
        return dst
    text = Normalizer(cfg, cache).normalize(src.read_text(encoding="utf-8"))
    dst.write_text(text, encoding="utf-8")
    return dst
