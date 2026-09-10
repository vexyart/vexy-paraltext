#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.12"
# dependencies = ["vexy-paraltext"]
# [tool.uv.sources]
# vexy-paraltext = { path = "..", editable = true }
# ///
# this_file: scripts/compare_models.py
"""Weigh jina against gemma on one book slice: pair counts, time, agreement, disagreements."""

import random
import sys
import time
from pathlib import Path

from loguru import logger

from vexy_paraltext import pipeline
from vexy_paraltext.config import load_config

logger.remove()
logger.add(sys.stderr, level="WARNING")
book = Path(sys.argv[1] if len(sys.argv) > 1 else "ebook-font-l10n/adrian-frutiger--typefaces-the-complete-works")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 1.05
res = {}
bk = pipeline.Book(book, load_config(book))
for model in ("jina", "gemma"):
    t = time.time()
    res[model] = pipeline.run_align(bk, model=model, limit=limit, threshold=threshold, out=Path(f"/tmp/cmp-{model}.tmx"))
    print(f"{model}: {len(res[model].units)} units, {time.time() - t:.0f}s (embedding cached after first run)")
j = {u["en"]: u for u in res["jina"].units}
g = {u["en"]: u for u in res["gemma"].units}
both = set(j) & set(g)
agree = sum(j[k] == g[k] for k in both)
print(f"shared en spans: {len(both)}, identical units: {agree}, only jina: {len(set(j) - both)}, only gemma: {len(set(g) - both)}")
random.seed(0)
for name, extra in (("only jina", set(j) - both), ("only gemma", set(g) - both)):
    print(f"\n== {name} (5 random)")
    for k in random.sample(sorted(extra), min(5, len(extra))):
        u = (j if name == "only jina" else g)[k]
        for lang, text in u.items():
            print(f"  {lang}: {text[:160]}")
        print()
print("== disagreements (5 random)")
diff = sorted(k for k in both if j[k] != g[k])
for k in random.sample(diff, min(5, len(diff))):
    print(f"  en: {k[:160]}")
    for lang in ("de", "fr"):
        if j[k].get(lang) != g[k].get(lang):
            print(f"  {lang} jina : {j[k].get(lang, '')[:160]}\n  {lang} gemma: {g[k].get(lang, '')[:160]}")
    print()
