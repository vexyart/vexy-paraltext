# this_file: src/vexy_paraltext/align.py
"""Find parallel sentences between two editions from their embeddings.

Method: margin-based bitext mining (Artetxe & Schwenk) with 1-1 and 2-1/1-2
candidates, mutual-best filtering, then a monotonic (longest increasing
subsequence) pass, since a book translation keeps the source order.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

import numpy as np

Span = tuple[int, ...]
K = 4
BLOCK = 2048
GAP_MIN_COS = 0.6


@dataclass(frozen=True)
class Link:
    """Aligned span pair: sentence index tuples on each side plus a margin score."""

    src: Span
    tgt: Span
    score: float


def with_bigrams(sentences: list[str]) -> tuple[list[str], list[Span]]:
    """Unigram plus adjacent-pair candidates, with their index spans."""
    texts = list(sentences)
    spans: list[Span] = [(i,) for i in range(len(sentences))]
    for i in range(len(sentences) - 1):
        texts.append(sentences[i] + " " + sentences[i + 1])
        spans.append((i, i + 1))
    return texts, spans


def _topk(a: np.ndarray, b: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """For each row of ``a``: indices and cosines of its ``k`` nearest rows in ``b``."""
    idx = np.empty((len(a), k), dtype=np.int64)
    val = np.empty((len(a), k), dtype=np.float32)
    for s in range(0, len(a), BLOCK):
        sims = a[s : s + BLOCK] @ b.T
        part = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        pv = np.take_along_axis(sims, part, axis=1)
        order = np.argsort(-pv, axis=1)
        idx[s : s + BLOCK] = np.take_along_axis(part, order, axis=1)
        val[s : s + BLOCK] = np.take_along_axis(pv, order, axis=1)
    return idx, val


def mine(a: np.ndarray, b: np.ndarray, *, threshold: float = 1.05) -> list[tuple[int, int, float]]:
    """Mutual-best candidate pairs (i in a, j in b) whose ratio margin beats ``threshold``."""
    k = max(1, min(K, len(a), len(b)))
    ia, va = _topk(a, b, k)
    ib, vb = _topk(b, a, k)
    mean_a, mean_b = va.mean(axis=1), vb.mean(axis=1)
    out = []
    for i in range(len(a)):
        j = int(ia[i, 0])
        if int(ib[j, 0]) != i:
            continue
        margin = float(va[i, 0]) / ((mean_a[i] + mean_b[j]) / 2 + 1e-9)
        if margin >= threshold:
            out.append((i, j, margin))
    return out


def _monotonic(links: list[Link]) -> list[Link]:
    """Longest chain of links increasing in both source and target position."""
    links = sorted(links, key=lambda l: (l.src[0], l.tgt[0]))
    tails: list[int] = []
    tail_idx: list[int] = []
    prev = [-1] * len(links)
    for n, link in enumerate(links):
        pos = bisect_left(tails, link.tgt[0])
        if pos == len(tails):
            tails.append(link.tgt[0])
            tail_idx.append(n)
        else:
            tails[pos] = link.tgt[0]
            tail_idx[pos] = n
        prev[n] = tail_idx[pos - 1] if pos else -1
    chain = []
    n = tail_idx[-1] if tail_idx else -1
    while n != -1:
        chain.append(links[n])
        n = prev[n]
    return chain[::-1]


def center(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Subtract the joint mean vector and renormalise: makes ratio margins independent of how compressed a model's space is."""
    mu = np.vstack([a, b]).mean(axis=0)
    ca, cb = a - mu, b - mu
    ca /= np.linalg.norm(ca, axis=1, keepdims=True) + 1e-9
    cb /= np.linalg.norm(cb, axis=1, keepdims=True) + 1e-9
    return ca, cb


def _fill_gaps(chain: list[Link], src_emb: np.ndarray, tgt_emb: np.ndarray, min_cos: float) -> list[Link]:
    """Between consecutive links, pair a lone unaligned sentence on each side if they are similar enough.

    Unigram rows of the embedding matrices come first, so sentence ``i`` is row ``i``.
    """
    out: list[Link] = []
    for a, b in zip([None, *chain], [*chain, None], strict=True):
        s_lo, t_lo = (a.src[-1] + 1, a.tgt[-1] + 1) if a else (0, 0)
        if b is not None and b.src[0] - s_lo == 1 and b.tgt[0] - t_lo == 1:
            cos = float(src_emb[s_lo] @ tgt_emb[t_lo])
            if cos >= min_cos:
                out.append(Link((s_lo,), (t_lo,), cos))
        if b is not None:
            out.append(b)
    return out


def align(
    src_spans: list[Span],
    src_emb: np.ndarray,
    tgt_spans: list[Span],
    tgt_emb: np.ndarray,
    *,
    threshold: float = 1.05,
    gap_min_cos: float = GAP_MIN_COS,
    center_vectors: bool = True,
) -> list[Link]:
    """Full pipeline: (center), mine, drop overlapping spans (best score wins), enforce order, fill 1-1 gaps."""
    if center_vectors:
        src_emb, tgt_emb = center(src_emb, tgt_emb)
    cands = [Link(src_spans[i], tgt_spans[j], s) for i, j, s in mine(src_emb, tgt_emb, threshold=threshold)]
    used_s: set[int] = set()
    used_t: set[int] = set()
    kept = []
    for link in sorted(cands, key=lambda l: -l.score):
        if used_s.isdisjoint(link.src) and used_t.isdisjoint(link.tgt):
            kept.append(link)
            used_s.update(link.src)
            used_t.update(link.tgt)
    return _fill_gaps(_monotonic(kept), src_emb, tgt_emb, gap_min_cos)
