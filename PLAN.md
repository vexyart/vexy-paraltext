---
this_file: PLAN.md
---

# Plan

## Done (0.1.0)

Pipeline runs end to end on the Frutiger trilingual book; see WORK.md for numbers. Issue 103 (config, LLM normalize stage, per-stage CLI, diskcache, parallelism) is implemented; the LLM stage is validated on a 30k-char slice, not yet on a whole book.

## Next

0. **Union of two models.** On King the model-only link sets are 400-1,000 per target and shared links agree 96-100%; aligning with jina and gemma and taking the union should add 10-20% units at no precision cost. Needs a conflict rule when both models link one pivot span to different targets (keep the higher margin).
1. **Measure normalize's effect on alignment yield.** Run the Frutiger book with normalize on (overnight) and compare unit count and spot-check precision against the 4,863 units from raw markdown. Decide the default of `[normalize] enabled` from that.
2. **Smaller normalize model.** Time `gemma-4-E4B` or a 4B-class model on the same chunks; if quality holds, the LLM pass drops from hours to under one hour per book.
3. **Trigram spans.** Only if inspection of the full-book TMX shows many 3-1 merges; each extra n-gram costs one more embedding pass.
4. **Multilingual single volumes** (`de-en`, `de-en-fr` folders): split the one markdown by language (fastText/lingua language ID per paragraph) and treat each as an edition.
5. **Batch run over all 40 books** and a coverage table in WORK.md; the scanned PDFs (35) go through docling OCR and need a Tesseract language pack or ocrmac per language.

## Release tooling — completed 2026-09-12

- [x] Provide verified Git-tag releases, a real dry run, same-tag retries, and private-data exclusions.
