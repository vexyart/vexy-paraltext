# this_file: src/vexy_paraltext/segment.py
"""Turn converter markdown into a clean list of sentences."""

from __future__ import annotations

import html
import re
from collections import Counter

import pysbd
import pysbd.languages
from loguru import logger

MIN_CHARS = 15
MAX_CHARS = 600
MAX_REPEATS = 2  # running heads, TOC entries repeat; body sentences do not
MAX_DIGIT_RATIO = 0.2
_SOFT_HYPHEN = "­"
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARK = re.compile(r"[*_`#>]+")
_HTML_TAG = re.compile(r"<[^>]+>")
_FIG_REF = re.compile(r"\s*/\d{1,3}/\s*")
_HYPHEN_BREAK = re.compile(r"(\w)[-\u2010]\s*\n\s*(\w)")
_SPACES = re.compile(r"[ \t]+")
_GLUED = re.compile(r"(?<=[a-zà-ÿ])([.!?])(?=[A-ZÀ-Ý])")
_LETTERS = re.compile(r"[^\W\d_]")
_DIGITS = re.compile(r"\d")
_FALLBACK_SPLIT = re.compile(r"(?<=[.!?…])[\"'”»)]?\s+(?=[\"'„«(]?[A-ZÀ-ÝĄĆĘŁŃÓŚŹŻČŠŽĞİŞ])")


def clean_markdown(text: str) -> list[str]:
    """Strip markdown/HTML decoration and return reflowed paragraphs."""
    text = html.unescape(text).replace(_SOFT_HYPHEN, "")
    text = _MD_IMAGE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _HTML_TAG.sub(" ", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        para = _SPACES.sub(" ", _MD_MARK.sub("", block.replace("\n", " "))).strip()
        para = _GLUED.sub(r"\1 ", _FIG_REF.sub(" ", para)).strip()
        if para:
            paragraphs.append(para)
    return paragraphs


def _segmenter(lang: str) -> pysbd.Segmenter | None:
    code = lang.split("-", maxsplit=1)[0]
    if code in pysbd.languages.LANGUAGE_CODES:
        return pysbd.Segmenter(language=code, clean=False)
    logger.warning("pysbd has no rules for {!r}, using regex splitter", lang)
    return None


def _keep(sentence: str) -> bool:
    n = len(sentence)
    letters = len(_LETTERS.findall(sentence))
    digits = len(_DIGITS.findall(sentence))
    return MIN_CHARS <= n <= MAX_CHARS and letters >= n * 0.5 and digits <= n * MAX_DIGIT_RATIO


def drop_repeats(sentences: list[str], max_repeats: int = MAX_REPEATS) -> list[str]:
    """Remove sentences that occur more than ``max_repeats`` times (running heads, TOC)."""
    counts = Counter(sentences)
    return [s for s in sentences if counts[s] <= max_repeats]


def split_sentences(text: str, lang: str) -> list[str]:
    """Markdown text -> sentences in reading order, junk removed."""
    seg = _segmenter(lang)
    out: list[str] = []
    for para in clean_markdown(text):
        parts = seg.segment(para) if seg else _FALLBACK_SPLIT.split(para)
        out.extend(s.strip() for s in parts if _keep(s.strip()))
    return drop_repeats(out)
