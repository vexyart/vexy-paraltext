---
this_file: README.md
---

# vexy-paraltext

Turn a folder of translated book editions into one compact TMX translation memory of aligned sentences.

```
book/
  en/Book.pdf        ->  book/book.tmx
  en/Book.md             stage 1: converter markdown, next to the source
  en/Book.norm.md        stage 2: LLM-normalized text
  de/Buch.djvu ...       (PDF, EPUB and DjVu editions)
  book/paraltext-cache/  stages 2-3: diskcache of LLM chunks and sentence vectors, converter scratch
```

A unit is written whenever the pivot sentence aligns in at least one other edition (`min_langs = 2`): with English A B C, German A B C and French A C you get A(en,de,fr), B(en,de), C(en,de,fr). Raise `min_langs` to require more editions. Sentences with no counterpart anywhere are dropped, not padded.

## Install

```bash
uv sync                          # runtime
npm install -g @shiftlabs/markit # PDF -> markdown (text-layer PDFs)
brew install djvulibre           # DjVu (djvutxt text layer; ddjvu renders scans for OCR)
uv sync --group ocr              # optional: docling, only for scanned PDFs
```

Embedding models are local GGUF files run through llama.cpp (Metal on Apple Silicon). Three are configured: `jina` (jina-embeddings-v5-text-nano, the default), `gemma` (EmbeddingGemma 300M) and `granite` (granite-embedding-311m-multilingual-r2). Paths and prompt prefixes are in `paraltext.example.toml`.

## Use

```bash
uv run vexy-paraltext run BOOK                 # all four stages
uv run vexy-paraltext convert BOOK             # stage 1: PDF/EPUB -> markdown
uv run vexy-paraltext normalize BOOK           # stage 2: LLM clean-up (needs LM Studio serving the model)
uv run vexy-paraltext embed BOOK               # stage 3: sentence vectors into the cache
uv run vexy-paraltext align BOOK --threshold 1.1 --limit 2000   # stage 4: TMX (dev slice)
uv run vexy-paraltext batch ./ebook-font-l10n  # every book folder under a root
```

Each stage reuses the markdown next to the sources and the vectors in `paraltext-cache/`; `--force` redoes convert and normalize. Options: `--model jina|gemma|granite|/path/model.gguf`, `--pivot en`, `--threshold` (margin cutoff, higher is stricter), `--min-langs N` (default 2), `--config paraltext.toml`.

## Which embedding model

Measured on whole books (King 15 editions, McLuhan 13, Manguel 10, Lakoff 6; details in `WORK.md` and `llm-embed/JINA-VS-GEMMA-VS-GRANITE.md`):

| | jina (default) | gemma | granite |
|---|---|---|---|
| strengths | most all-language units, never collapses on a language, fastest | 2-8% more pairs on major Western languages and Chinese | most even across languages, Apache 2.0, best on cs/hu/lt |
| weakness | CC BY-NC weights | Lithuanian at 32-42% yield, Hungarian weak | 7% fewer pairs overall, slowest |

Where two models link the same sentence they pick the same translation 93-100% of the time, so the choice only moves recall. Vectors are mean-centred before mining; without that Granite finds almost nothing and the other two lose 4-12%.

## Results on the collection

37 of 40 books in `ebook-font-l10n/` produce a TMX, 131k translation units in total (normalize stage off). The three without one are single editions or single trilingual volumes. Per-book table in `WORK.md`.

## Configure

Copy `paraltext.example.toml` to `paraltext.toml` in the book folder, the working directory, or `~/.config/vexy-paraltext/`. It holds model paths and prompt prefixes, the LM Studio model and URL for normalization, worker counts and the alignment threshold. Set `[normalize] enabled = false` to skip the LLM pass: the Frutiger book then takes ~5 min end to end instead of hours.

## How it works

1. **Convert** (editions in parallel, OCR one at a time in a child process): `markit` for PDFs with a text layer (2 s per 470-page book, PyMuPDF fallback when markit rejects or truncates the text), `docling` OCR for scans and for image-only EPUBs (page images stacked into a PDF), `epub2md.py` for EPUB, `djvutxt` for DjVu (rendered with `ddjvu` and OCRed when there is no text layer). Cyrillic text layers stored as cp1251 bytes are recoded.
2. **Normalize** (chunks in parallel, diskcache): a local LLM through LM Studio's OpenAI-compatible API rewrites each ~3000-char chunk into plain paragraphs of plain sentences: broken words joined, letter-spaced headings and ALL CAPS turned into sentence case, page furniture and markdown dropped.
3. **Segment**: strip leftover markup, rejoin hyphenated line breaks, split with `pysbd` (regex fallback for languages it lacks), drop repeats and digit-heavy lines.
4. **Embed**: every sentence plus every adjacent pair (so 2-1 and 1-2 alignments are possible); vectors cached per sentence in diskcache so re-runs only embed new text.
5. **Align** (target languages in parallel): vectors are mean-centred (a compressed space such as Granite's otherwise never clears the margin), then margin-based mining (mutual nearest neighbours scored against their k-NN neighbourhood), overlapping spans resolved by score, a longest-increasing-subsequence pass keeps only links in book order, then lone sentences between two links are paired if similar enough.
6. **Write**: one `<tu>` per line, no padding, `xml:lang` per `<tuv>`. XML 1.0-forbidden characters are removed from text and metadata; XML markup and attribute values are escaped.

## Develop

```bash
uv sync --all-groups
uv run pytest                                    # 80% coverage floor
uv run ruff format --check && uv run ruff check && uv run ty check src/
uv run scripts/compare_lakoff.py BOOK 0 1.05 jina,gemma,granite   # per-language yield, agreement, multi-way units
uv run scripts/compare_models.py BOOK 2000                        # jina vs gemma on a slice, with sample disagreements
```
