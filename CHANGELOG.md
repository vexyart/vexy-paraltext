---
this_file: CHANGELOG.md
---

# Changelog

## Unreleased

- TMX output removes XML 1.0-forbidden characters from segment text and metadata, and quotes attribute values safely. Legal Unicode and XML whitespace remain intact.
- Repaired all three affected collection TMX files (19 forbidden characters); all 37 files parse successfully, retaining 131,295 translation units.

## 0.1.0 (2026-09-09)

- Package scaffold (`uv`, `src/` layout, ruff, ty, pytest at 84% coverage).
- Pipeline: convert (markit / docling / epub2md), segment (pysbd), embed (llama.cpp GGUF, cached), align (margin mining + monotonic filter, 1-1 and 2-1 spans), TMX writer.
- CLI `vexy-paraltext run|batch`.
- PDF converter bake-off and jina-vs-gemma comparison recorded in WORK.md.
- Issue 103: `paraltext.toml` config (`config.py`), LLM normalize stage through LM Studio (`normalize.py`), per-stage CLI commands `convert|normalize|embed|align` with `run` chaining them, diskcache for LLM chunks and per-sentence embeddings, parallel conversion / normalization / alignment. Default embedding model switched to gemma (more units at equal precision).
- Issue 106: Granite 311m r2 added as third model; vectors are mean-centred before mining (`[embed] center`, default on) which turns Granite from unusable into competitive and lifts jina/gemma 4-12%; default model switched to jina after the 15-language King test; `min_langs` defaults to 2; converter output lives next to the sources (no hidden folders, `paraltext-cache/` for diskcache); DjVu support via djvulibre.
- Batch over the whole collection: 37 of 40 books produce a TMX (see WORK.md table). Hardening from the run: docling OCR isolated in a child process (segfaults skip an edition), image-only EPUBs OCRed via a stacked PDF, PyMuPDF fallback when markit rejects or truncates a text layer, cp1251 mojibake repair for Cyrillic editions, sparse-text-layer detection, unconvertible editions skipped instead of failing the book.
- Six-language (Lakoff) and fifteen-language (King) tests; findings in WORK.md and `llm-embed/JINA-VS-GEMMA-VS-GRANITE.md` section 12. Scanned PDFs now OCR one at a time; image-only EPUBs raise a clear error; identical (untranslated) pairs are dropped from the TMX.
