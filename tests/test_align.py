# this_file: tests/test_align.py
"""Alignment on synthetic embeddings."""

import numpy as np

from vexy_paraltext.align import Link, _fill_gaps, _monotonic, align, center, mine, with_bigrams


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_with_bigrams_when_three_sentences_then_five_candidates():
    texts, spans = with_bigrams(["a", "b", "c"])
    assert texts == ["a", "b", "c", "a b", "b c"]
    assert spans == [(0,), (1,), (2,), (0, 1), (1, 2)]


def test_with_bigrams_when_empty_then_empty():
    assert with_bigrams([]) == ([], [])


def test_mine_when_target_is_noisy_copy_then_mutual_pairs_found(rng):
    a = _unit(rng.normal(size=(50, 16)).astype(np.float32))
    b = _unit(a + 0.05 * rng.normal(size=a.shape).astype(np.float32))
    pairs = mine(a, b, threshold=1.05)
    assert len(pairs) >= 45
    assert all(i == j for i, j, _ in pairs)


def test_mine_when_unrelated_then_few_pairs(rng):
    a = _unit(rng.normal(size=(40, 16)).astype(np.float32))
    b = _unit(rng.normal(size=(40, 16)).astype(np.float32))
    assert len(mine(a, b, threshold=1.3)) < 10


def test_monotonic_when_one_link_out_of_order_then_dropped():
    links = [Link((0,), (0,), 1.0), Link((1,), (5,), 1.0), Link((2,), (2,), 1.0), Link((3,), (3,), 1.0)]
    kept = _monotonic(links)
    assert [l.src for l in kept] == [(0,), (2,), (3,)]


def test_monotonic_when_empty_then_empty():
    assert _monotonic([]) == []


def test_align_when_target_merges_two_sentences_then_bigram_link(rng):
    src = _unit(rng.normal(size=(6, 16)).astype(np.float32))
    # target sentence 1 = merge of source 1 and 2
    tgt_sent = np.vstack([src[0], _unit((src[1] + src[2])[None])[0], src[3], src[4], src[5]])
    src_texts, src_spans = with_bigrams([f"s{i}" for i in range(6)])
    tgt_texts, tgt_spans = with_bigrams([f"t{i}" for i in range(5)])

    def emb(base: np.ndarray, spans: list) -> np.ndarray:
        return _unit(np.vstack([base[list(s)].sum(axis=0) for s in spans]))

    links = align(src_spans, emb(src, src_spans), tgt_spans, emb(tgt_sent, tgt_spans), threshold=1.0)
    pairs = {(l.src, l.tgt) for l in links}
    assert ((1, 2), (1,)) in pairs
    assert ((0,), (0,)) in pairs
    used = [i for l in links for i in l.src]
    assert len(used) == len(set(used)), "no source sentence in two links"


def test_fill_gaps_when_lone_pair_between_links_then_added():

    src = _unit(np.eye(4, dtype=np.float32))
    tgt = src.copy()
    chain = [Link((0,), (0,), 1.5), Link((2,), (2,), 1.5)]
    out = _fill_gaps(chain, src, tgt, 0.6)
    assert [l.src for l in out] == [(0,), (1,), (2,)]
    assert out[1].score == 1.0


def test_fill_gaps_when_gap_dissimilar_then_not_added():

    src = _unit(np.eye(4, dtype=np.float32))
    tgt = np.roll(src, 1, axis=0)  # sentence 1 no longer matches
    tgt[0], tgt[2] = src[0], src[2]
    chain = [Link((0,), (0,), 1.5), Link((2,), (2,), 1.5)]
    assert _fill_gaps(chain, src, tgt, 0.6) == chain


def test_center_when_shared_offset_then_removed_and_unit_norm(rng):

    base = rng.normal(size=(20, 8)).astype(np.float32)
    a = _unit(base + 5.0)  # heavy common offset: everything looks alike
    b = _unit(base + 5.0 + 0.01 * rng.normal(size=base.shape).astype(np.float32))
    assert float(np.mean(a[:10] @ a[10:].T)) > 0.9, "raw space is compressed"
    ca, cb = center(a, b)
    assert np.allclose(np.linalg.norm(ca, axis=1), 1.0, atol=1e-5)
    assert float(np.mean(ca[:10] @ cb[10:].T)) < 0.3, "centering spreads unrelated pairs"
    assert float(np.mean(np.sum(ca * cb, axis=1))) > 0.9, "true pairs stay close"


def test_align_when_space_compressed_then_centering_recovers_links(rng):
    src = _unit(rng.normal(size=(30, 16)).astype(np.float32) + 4.0)
    tgt = _unit(rng.normal(size=(30, 16)).astype(np.float32) * 0.05 + src)
    spans = [(i,) for i in range(30)]
    raw = align(spans, src, spans, tgt, threshold=1.05, center_vectors=False)
    centered = align(spans, src, spans, tgt, threshold=1.05, center_vectors=True)
    assert len(centered) > len(raw)
    assert len(centered) >= 25
