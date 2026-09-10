#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.12"
# dependencies = ["vexy-paraltext"]
# [tool.uv.sources]
# vexy-paraltext = { path = "..", editable = true }
# ///
# this_file: scripts/compare_lakoff.py
"""Multi-language embedding comparison (jina vs gemma) on one book folder.

Usage: compare_lakoff.py BOOK [LIMIT] [THRESHOLD]
Reports per model: embedding speed, per-target links, cosine/margin statistics, units by language count,
and per-target agreement between the two models.
"""

import random
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from loguru import logger

from vexy_paraltext import pipeline
from vexy_paraltext.config import load_config

logger.remove()
logger.add(sys.stderr, level="WARNING")
book = Path(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 1.05
bk = pipeline.Book(book, load_config(book))
models = sys.argv[4].split(",") if len(sys.argv) > 4 else ["jina", "gemma"]
if "--no-center" in sys.argv:
    bk.cfg.embed.center = False
random.seed(0)

rows = {}
results = {}
for model in models:
    if "--fresh" in sys.argv:
        shutil.rmtree(bk.cache / "cache" / "embeddings", ignore_errors=True)  # fresh timing
    t = time.time()
    eds = pipeline.run_embed(bk, model=model, limit=limit or None)
    n_texts = sum(len(ed.spans) for ed in eds.values())
    embed_s = time.time() - t
    t = time.time()
    res = pipeline.run_align(bk, eds, threshold=threshold, min_langs=2, out=Path(f"/tmp/lakoff-{model}.tmx"))
    align_s = time.time() - t
    results[model] = (eds, res)
    pivot = next(iter(res.units[0])) if res.units else "en"
    src = eds[pivot]
    per_lang = {}
    for lang, links in res.links.items():
        ed = eds[lang]
        cos = [float(src.emb[src.spans.index(lk.src)] @ ed.emb[ed.spans.index(lk.tgt)]) for lk in links]
        rnd = [float(src.emb[random.randrange(len(src.spans))] @ ed.emb[random.randrange(len(ed.spans))]) for _ in range(500)]  # noqa: S311
        per_lang[lang] = (len(links), np.mean(cos) if cos else 0, np.mean(rnd), np.mean([lk.score for lk in links]) if links else 0)
    nlang = Counter(len(u) for u in res.units)
    rows[model] = (n_texts, embed_s, align_s, per_lang, nlang, res.per_lang)

print(f"book: {book.name}  limit: {limit or 'all'}  threshold: {threshold}  center: {bk.cfg.embed.center}")
for model, (n_texts, embed_s, align_s, per_lang, nlang, per_sent) in rows.items():
    print(f"\n== {model}: {n_texts} texts embedded in {embed_s:.0f}s ({n_texts / embed_s:.0f}/s), align {align_s:.0f}s")
    print("sentences:", ", ".join(f"{k} {v}" for k, v in per_sent.items()))
    print(f"{'target':>6} {'links':>6} {'yield%':>7} {'cos(link)':>9} {'cos(rand)':>9} {'margin':>7}")
    for lang, (n, c, r, m) in sorted(per_lang.items()):
        print(f"{lang:>6} {n:>6} {100 * n / per_sent[lang]:>6.1f}% {c:>9.3f} {r:>9.3f} {m:>7.3f}")
    print("units by number of languages:", dict(sorted(nlang.items())))

for a, b in [(models[i], models[j]) for i in range(len(models)) for j in range(i + 1, len(models))]:
    print(f"\n== agreement per target, {a} vs {b} (same pivot span -> same translation)")
    ra, rb = results[a][1], results[b][1]
    for lang in sorted(ra.links):
        ma = {lk.src: lk.tgt for lk in ra.links[lang]}
        mb = {lk.src: lk.tgt for lk in rb.links[lang]}
        both = set(ma) & set(mb)
        same = sum(ma[k] == mb[k] for k in both)
        print(
            f"{lang:>6} {a} {len(ma):>5} {b} {len(mb):>5} shared {len(both):>5} identical {same:>5} ({100 * same / max(1, len(both)):.0f}%) only-{a} {len(set(ma) - both):>5} only-{b} {len(set(mb) - both):>5}"
        )

eg, rg = results[models[-1]]
print(f"\n== sample units present in every language ({models[-1]})")
full = [u for u in rg.units if len(u) == len(eg)]
for u in random.sample(full, min(3, len(full))):
    for lang, text in u.items():
        print(f"  {lang}: {text[:140]}")
    print()
