---
this_file: AGENTS.md
---

# AGENTS.md

Landmines you cannot see from the code. Prune a line once the root cause is fixed in code or tooling.

## Scope

`vexy-paraltext`: Python package that turns each book folder in `ebook-font-l10n/<slug>/<lang>/` into one compact TMX of sentence pairs that align across all language editions. Non-alignable text is dropped, not padded. Spec: `issues/102.md`.

## Private data (not in git, never commit)

- `ebook-font-l10n/` is a symlink to `/Volumes/Puck4T-Data/Puck4T-Data2/ebook/ebook-font-l10n` (external volume, may be unmounted). Use `find -L`; plain `find` does not descend. Its `catalog.yaml` and `README.md` say per edition whether a PDF is `TruePDF`, `OCRed`, or `Scanned` (no text layer). 76 EPUB + 87 PDF; 45 true, 35 scanned.
- `llm-embed/` is a separate project (embedding benchmark), gitignored here. Read its `AGENTS.md` and `JINA-VS-GEMMA-VS-GRANITE.md` before choosing embedding settings; do not import from it.
- Dev fixture: `ebook-font-l10n/adrian-frutiger--typefaces-the-complete-works/` (de, en, fr; all TruePDF, 60 to 130 MB, ~460 pages each). Develop on a page range, not the whole book.

## Models (GGUF, local, exact paths)

- Granite: `/Volumes/Falstaff4T/RomeoData2/lmstudio/models/mykor/granite-embedding-311m-multilingual-r2-GGUF/granite-embedding-311M-multilingual-r2-Q8_0.gguf` (no prefix, CLS pooling, GGUF context 8192 not 32k). Its raw space is compressed (random pairs cosine 0.80); mining only works with `[embed] center = true` (default). Never compare models with centering off.

- Gemma: `/Volumes/Falstaff4T/RomeoData2/lmstudio/models/mntcloud/embeddinggemma-300m-Q8_0-better-gguf/embeddinggemma-300M-Q8_0.gguf`
- Jina: `/Volumes/Falstaff4T/RomeoData2/lmstudio/models/jinaai/jina-embeddings-v5-text-nano-text-matching/v5-nano-text-matching-Q8_0.gguf`
- Both on an external volume; `Embedder._model` raises `FileNotFoundError` if missing.
- llama.cpp encoder models abort with `GGML_ASSERT(n_ubatch >= n_tokens)` when a batch exceeds `n_ubatch`; `embed.py` budgets batches by token count (4096) and clips texts to 512 tokens. Keep that when touching batching.
- Prefixes are load-bearing (measured in `llm-embed`): Jina text-matching needs `"Query: "` on both sides (similarity gap 0.46 without, 0.70 with). Gemma needs `"task: sentence similarity | query: "`. Gemma context is 2,048 tokens; fp16 is unsupported.
- EmbeddingGemma GGUFs converted before mid-2026 lack the dense projection layers and return wrong vectors. The `mntcloud ... better-gguf` file above is the fixed one; do not swap in another Gemma GGUF without checking.
- Jina nano weights are CC BY-NC; fine for this research use, not for shipping.

## LLM normalize stage (issue 103)

- Talks to LM Studio's server (`lms server start`, port 1234) with the OpenAI chat API; the model id must be one `curl localhost:1234/api/v0/models` lists (e.g. `gemma-4-26b-a4b-it-qat-mxfp8`). LM Studio JIT-loads it on the first request, so the first chunk takes ~1 min.
- Measured 2026-09-09 on this Mac: 28 tok/s at 1 request, 57 tok/s aggregate at 4 concurrent, 50 at 8. A 470-page edition is ~350k output tokens, so ~2 h per edition; the whole Frutiger book is an overnight job. `[normalize] enabled = false` skips it.
- `ternary-bonsai-27b-mlx-lossless-1.75bpw` returned HTTP 400 from the chat endpoint; not usable as listed. gemma-4-12b dense was not timed (a dense 12B will be slower than the 26B-A4B MoE).
- Prompt text lives in `normalize.py`; bump `PROMPT_VERSION` when you change it, otherwise cached chunks from the old prompt are reused.

## Conversion tools

- EPUB: `/Users/adam/bin/epub2md.py` (uv script, `fire` CLI). Call as `uv run -s /Users/adam/bin/epub2md.py <epub_or_dir> --output_dir X --merge`. Without `--merge` it writes one `.md` per chapter; it skips existing output unless `--force`.
- PDF: `markit` (npm `@shiftlabs/markit`, not on PyPI) for PDFs with a text layer: 2 s per 470-page book, column-aware. It does not OCR; `convert.has_text_layer` routes scans to docling (`uv sync --group ocr`, ~3 s per page). docling dies silently (no traceback, a leaked-semaphore warning) on some scans, even alone; `convert.ocr_pdf_isolated` runs it in a child process (`python -m vexy_paraltext.ocr`) so the edition is skipped with a ConvertError and the batch survives. Scans still run one at a time.
- Collection traps: at least 8 EPUBs are image-only (Lakoff pl, Munari it, Smeijers en+zh, Noordzij es+it, Zapf es, Hochuli en+it); `epub_to_markdown` stacks their images into a PDF and OCRs it (~20-40 min each); Lakoff `zh` is a bilingual textbook that quotes the English examples inline, so English-to-English links appear (dropped by `pipeline.is_untranslated`). pysbd has no rules for cs, da, hu, lt, pt, ro, sv, tr: those get the regex splitter, expect more 2-1 spans. Do not swap in pymupdf4llm/liteparse/anydoc; bake-off in WORK.md shows why.
- markit leaves soft hyphens (U+00AD) and occasional spurious mid-word spaces ("Ant wortbrief"); `segment.py` strips the former, the latter is not fixable and lowers similarity slightly.
- Outputs sit next to the sources: `<lang>/<stem>.md` and `<stem>.norm.md`; diskcache and converter scratch in `<book>/paraltext-cache/` (~100 MB of vectors per model per book). Older runs (before 2026-09-09 evening) wrote into `<book>/.paraltext/`; those folders are stale, delete or move them. `--force` only redoes convert and normalize.
- DjVu: `djvutxt` (brew `djvulibre`); the only DjVu in the collection (Lakoff ru) has a text layer, 0.24 s. Scans without one go through `ddjvu -format=pdf` then docling.

## Tooling (modern-python)

- `uv` for everything: `uv add` / `uv remove` / `uv sync --all-groups` / `uv run <cmd>`. Never bare `pip`, never `uv pip install`, never activate `.venv` by hand, never edit dependency lists in `pyproject.toml` manually.
- Layout: `uv init --package`, `src/vexy_paraltext/`, build backend `uv_build`. `requires-python = ">=3.12"`. Commit `uv.lock`.
- Dev tools live in `[dependency-groups]` (PEP 735), not `[project.optional-dependencies]`: `lint = ["ruff", "ty"]`, `test = ["pytest", "pytest-cov"]`.
- Lint/format: ruff only (`select = ["ALL"]` plus explicit ignores). Type check: `ty`, config under `[tool.ty.environment]` (`python-version = "3.12"`), not `[tool.ty]`.
- Tests: `uv run pytest` (coverage floor 80% in `[tool.pytest] addopts`). Check: `uv run ruff format --check && uv run ruff check && uv run ty check src/`.
- One-off experiments (PDF tool bake-off, embedding probes) go in `scripts/` as PEP 723 scripts (`# /// script` header) run with `uv run -s`, or use `uv run --with <pkg>`; they must not become project dependencies until chosen.
- Embedding runs and PDF conversion are slow; run them with `run_in_background` and cache intermediates next to the book (`<book>/<lang>/*.md`, embeddings as `.npz`) so reruns skip finished stages.
