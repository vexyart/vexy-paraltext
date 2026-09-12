---
this_file: WORK.md
---

# Work log

## 2026-09-11: shared uubed inference

- Replaced duplicated llama.cpp inference with the shared uubed engine and
  configuration-sensitive compact-vector cache. Preserved joint mean-centering,
  explicit prompts and token-budget defaults.
- Added backend/dimensions/precision CLI overrides and explicit profiles for GGUF
  paths, plus API examples and an optional MLX extra. Existing `batch.toml` is untouched.
- Full suite: 112 passed, 93.49% coverage; ruff and ty pass. A real copied-data
  EPUB-to-TMX run produced 63 units for float32/int8, 62 identical and one changed
  alignment; cold/warm cache reads are stable. Root research/301 holds reproducible
  scripts and sanitized measurements; private artifacts remain in testdata.


## 2026-09-10: TMX forbidden-character repair

- Reproduced the writer failure with regression tests before editing: XML escaping alone left forbidden characters intact. Added a shared XML 1.0 character filter at the serialization boundary and standard-library attribute quoting; no new dependencies. Character ranges follow https://www.w3.org/TR/xml/#charsets.
- Tests cover all forbidden C0 controls, surrogate boundaries, U+FFFE/U+FFFF, metadata escaping, empty cleaned segments, literal character-reference text, legal whitespace, and BMP/supplementary Unicode boundaries.
- Audited all 37 TMX files recursively through the collection symlink. Removed exactly 19 characters in three files: Frutiger Typefaces (1 U+0008), Elam Geometry of Design (7 U+0007), Bringhurst Elements (1 U+0004 and 10 U+0008).
- Parsed cleaned bytes before atomic replacement and re-read every resulting file. All 37 parse successfully, all 131,295 translation units remain, and the 34 unaffected files retain identical SHA-256 hashes. Changed files differ only by forbidden-character removal; repeat cleaning is a no-op. Per-file hashes and counts are in the temporary audit `/tmp/paraltext-tmx-audit.json` (private collection data, not committed).
- Baseline: 71 tests passed, 91.42% coverage. Final: 106 tests passed, 91.47% coverage (TMX module 100%); `ruff format --check`, `ruff check`, and `ty check src/` all passed.

## 2026-09-09: 0.1.0

### PDF-to-markdown bake-off

Samples: 21 pages each of the Frutiger en/de/fr TruePDFs (image-heavy, two-column captions), 11 pages of an OCRed Polish PDF (Hochuli), 11 pages of a scanned English PDF with no text layer (Bringhurst). Script: `scripts/bake_pdf.py`; npm CLIs timed with `/usr/bin/time`.

| tool | frutiger-en 21 pp | ocr-pl 11 pp | scanned-en 11 pp | column order | verdict |
|---|---|---|---|---|---|
| markit (npm, Rust) | 0.11 s | 1.3 s | 0.29 s, no text | correct, one paragraph per block | **chosen** for text-layer PDFs; full 469-page book in 1.75 s |
| anydoc (npm, Rust) | 0.08 s | fails ("needs OCR") | fails | interleaves the two columns | rejected |
| pymupdf4llm | 5.9 s | 84 s | 11 s | correct | OCRs every image page with Tesseract (eng only); 50x slower than markit, drops line-break hyphens ("play ed") |
| liteparse | 5.8 s | 4.0 s | 2.1 s | spatial: columns side by side on the same line | rejected; OCRs images too |
| docling | 59 s | 152 s | 37 s, good OCR | correct | ~3 s/page; **OCR fallback only** (scanned PDFs) |
| marker | crash (worker died) | | | | rejected |
| edgequake-pdf2md | not run | | | | VLM-based, needs a vision model per page |
| deepdiy/pdf2md | not run | | | | YOLO layout model, prebuilt binary; markit already solves the text-layer case |
| mineru | installed, not run | | | | multi-GB model download for the same job |

Collection: 76 EPUB, 87 PDF (45 TruePDF, 35 scanned, rest OCRed). markit covers EPUB-free PDFs with text; docling covers the 35 scans at ~20 min per book.

### Segmentation

pysbd covers en/de/fr/es/it/pl/ru/zh/ja/ar/nl... but not pt/tr/ro/cs/lt/hu/sv; those get a regex splitter. Frutiger: 14,439 en / 14,512 de / 13,140 fr sentences after junk filters (min 15 chars, half letters, ≤20% digits, repeats >2 dropped).

### Embedding models on the 2000-sentence slice (threshold 1.05)

| model | units (en+de+fr) | en-de links | en-fr links | embed time, 4000 texts |
|---|---|---|---|---|
| jina v5 nano text-matching Q8 | 620 | 1206 | 927 | ~10 s |
| embeddinggemma 300m Q8 | 782 | 1363 | 1108 | ~20 s |

Shared en spans 469, identical units 462 (98.5%). Disagreements are span-boundary choices, both readable. The 313 gemma-only units sampled as correct translations; so were the 151 jina-only ones. Gemma gives ~26% more units at the same threshold with no visible precision loss; jina is twice as fast. Default stays `jina` for speed; use `--model gemma` when recall matters. (Full-book numbers below.)

### Full book (Frutiger, 3 languages)

Sentences after filters: en 14,439 / de 14,512 / fr 13,140 (before the repeat/digit filters; those trim a few hundred). Wall time includes markit conversion (cached after the first run), segmentation, embedding of unigrams + bigrams (~28k texts per language), alignment and TMX writing.

| model | wall time | en-de links | en-fr links | units (all 3 langs) | TMX size |
|---|---|---|---|---|---|
| jina | 297 s | ~8.0k | ~6.6k | 4,296 | 2.05 MB |
| gemma | 336 s | 8,575 | 7,153 | 4,863 | 2.19 MB |

Threshold sweep on cached embeddings (alignment only, ~27 s per model):

| threshold | jina units | gemma units | shared en spans | identical |
|---|---|---|---|---|
| 1.00 | 4,842 | 5,191 | 3,356 | 3,260 |
| 1.05 | 4,296 | 4,863 | 3,005 | 2,946 |
| 1.10 | 2,296 | 2,870 | 1,500 | 1,490 |
| 1.15 | 882 | 759 | 423 | 423 |

Where both models align the same English span they agree on the translation 97-99% of the time. Gemma finds 10-25% more units at 1.0-1.1 and its extras spot-check as correct; jina embeds about 40% faster. The default threshold stays 1.05: 1.0 admits a visible trickle of caption/footnote mismatches, 1.1 halves the yield.

Decision: **gemma is the better aligner for this task**; jina is the faster one. The CLI default is now `gemma`; `--model jina` for quick passes.

Yield: 4.9k trilingual units out of ~14k sentences per edition. The book is a heavily illustrated monograph; roughly half the sentences are captions, specimen text and running heads that do not align cleanly, which is the intended "omit what is not parallelizable" behaviour.

### Issue 103: config, LLM normalize, staged CLI, diskcache, parallelism

- `paraltext.toml` (see `paraltext.example.toml`) found in book folder, cwd or `~/.config/vexy-paraltext/`; `--config` overrides.
- Stages are separate commands (`convert`, `normalize`, `embed`, `align`), `run` chains them; every stage reuses the previous stage's files in `.paraltext/`.
- Normalize: LM Studio chat API, chunks of ~3000 chars on paragraph boundaries, thread pool, retries with backoff, truncated answers split the chunk. Prompt sample on the French front matter turned letter-spaced headings and the TOC table into plain sentences; on a German/English/French body chunk it fixed "sa me" -> "same" and removed heading markers.
- Throughput of `gemma-4-26b-a4b-it-qat-mxfp8` via LM Studio (MLX): 28 tok/s single, 57 tok/s at 4 concurrent requests, 50 at 8. One Frutiger edition is ~350k output tokens, so ~2 h per edition with normalize on; `enabled = false` keeps the 5-minute path. `ternary-bonsai-27b-mlx-lossless-1.75bpw` cannot load ("No LM Runtime found for model format 'torchSafetensors'"); gemma-4-12b dense not timed.
- Caches: `diskcache` (SQLite). Normalized chunks keyed by model + prompt version + text; embeddings keyed by model + sentence, so a changed segmentation only re-embeds new sentences.
- Parallel: editions convert in parallel (markit subprocesses), normalize chunks in a thread pool, alignment per target language in threads (numpy releases the GIL). Embedding stays sequential on one llama.cpp model.

### Six-language test: Lakoff & Johnson, *Metaphors We Live By*

Editions: 10 folders; ar, cs, de are scans (docling OCR; three in parallel crashed, one at a time works, so OCR now runs serially), pl is an image-only EPUB (154 PNGs, now a clear `ConvertError`). The six text editions (en, es, fr, it, tr, zh) converted in 5.7 s.

Full run, threshold 1.05, en pivot:

| target | jina links / yield | gemma links / yield | identical where shared |
|---|---|---|---|
| es | 2,520 / 57% | 2,875 / 65% | 98% |
| fr | 2,159 / 62% | 2,564 / 73% | 99% |
| it | 3,119 / 73% | 3,462 / 81% | 100% |
| tr | 2,494 / 53% | 2,979 / 64% | 99% |
| zh | 1,693 / 31% | 2,084 / 38% | 99% |

Six-language units: jina 305, gemma 423. Embedding 53.7k texts: jina 270 s, gemma 254 s. The Chinese edition quotes English examples inline, so the aligner matched English to English; `pipeline.is_untranslated` now drops such pairs. Full analysis in `llm-embed/JINA-VS-GEMMA-VS-GRANITE.md` section 12.

#### Granite 311m r2 and mean-centering

`ibm-granite/granite-embedding-311m-multilingual-r2` (Q8_0 GGUF, no prefix, 161 texts/s: the slowest of the three) mined almost nothing with the raw ratio margin: 145 es links (3%) against jina's 2,520, because its space is compressed (random cross-language pairs at cosine 0.80, true pairs at 0.97, so the best neighbour is never 5% better than the k-NN mean). Subtracting the joint mean vector before mining (`[embed] center = true`, now the default) fixes the scale and helps every model:

| target | jina raw -> centered | gemma raw -> centered | granite raw -> centered |
|---|---|---|---|
| es | 2,522 -> 2,811 | 2,875 -> 2,994 | 145 -> 2,578 |
| fr | 2,159 -> 2,449 | 2,564 -> 2,642 | 147 -> 2,258 |
| it | 3,127 -> 3,367 | 3,458 -> 3,498 | 228 -> 3,168 |
| tr | 2,494 -> 2,938 | 2,979 -> 3,120 | 83 -> 2,262 |
| zh | 1,694 -> 2,128 | 2,083 -> 2,325 | 255 -> 1,834 |
| six-language units | 233 -> 328 | 335 -> 431 | 3 -> 209 |

Centered, the ranking on Lakoff is gemma > jina > granite (granite 8-23% below jina per target, worst on Turkish), agreement 95-98% wherever two models link the same span.

### Fifteen-language test: Stephen King, *On Writing*

13 EPUBs + 2 TruePDFs (hu, ru), all converted in 2.5 s. 3.6k-4.9k sentences per edition; pysbd covers en, de, es, it, pl, ru, zh; cs, da, hu, lt, pt, ro, sv, tr use the regex splitter. Full run, threshold 1.05, en pivot, jina vs gemma:

| target | jina links / yield | gemma links / yield | shared identical | winner |
|---|---|---|---|---|
| cs | 2,724 / 69% | 2,554 / 64% | 96% | jina |
| da | 3,365 / 84% | 3,278 / 82% | 99% | jina |
| de | 3,345 / 68% | 3,450 / 70% | 99% | gemma |
| es | 2,933 / 72% | 3,161 / 78% | 98% | gemma |
| hu | 1,848 / 46% | 1,684 / 42% | 96% | jina |
| it | 3,352 / 80% | 3,478 / 83% | 99% | gemma |
| lt | 1,370 / 33% | 883 / 21% | 92% | jina |
| pl | 2,926 / 68% | 3,015 / 70% | 97% | gemma |
| pt | 3,492 / 79% | 3,722 / 84% | 99% | gemma |
| ro | 3,254 / 78% | 2,975 / 72% | 98% | jina |
| ru | 3,121 / 70% | 3,329 / 75% | 99% | gemma |
| sv | 2,948 / 64% | 2,937 / 64% | 98% | tie |
| tr | 3,072 / 74% | 3,283 / 79% | 98% | gemma |
| zh | 2,751 / 77% | 2,981 / 84% | 99% | gemma |

Fifteen-language units: jina 98, gemma 47. Units with 10+ languages: jina 2,196, gemma 2,214. Embedding 127k texts: jina 592 s (215/s), gemma 648 s (197/s).

Gemma wins the eight languages that are in Jina's 15-language backbone list (de, es, it, pl, pt, ru, tr, zh); Jina wins the six that are in neither model's training list by name (cs, da, hu, lt, ro, sv), by up to 55% on Lithuanian. The "all languages" requirement is dominated by the weakest language, so on this book jina doubles the fifteen-way yield.

Three models, centred (the numbers above were uncentred):

| | jina | gemma | granite |
|---|---|---|---|
| total links, 14 targets | 41,625 | 41,274 | 38,901 |
| best on | da, ro, sv | de, es, it, pl, pt, ru, tr, zh | cs, hu, lt |
| units in all 15 editions | 176 | 98 | 127 |
| units in 10+ editions | 2,362 | 2,348 | 2,064 |
| embed 127k texts | 559 s | 608 s | 701 s |

Decision (issue 106 item 2): default model is now **jina**; gemma for all-major-language sets; granite when a permissive licence or Baltic/Finno-Ugric coverage matters. Full write-up with eight observations: `llm-embed/JINA-VS-GEMMA-VS-GRANITE.md` sections 2.2 and 12.

### Ten-language test: Manguel, *A History of Reading* (two Chinese editions)

8 EPUB/text PDFs converted in seconds; zh-hans and zh-hant are scans (docling OCR, ~25 min each; the run with three parallel OCRs crashed, serial works). Same translator for both Chinese editions (Wu Changjie, Taiwan 1999 / Beijing 2002).

| target | jina | gemma | granite |
|---|---|---|---|
| es / fr / it / pt / ro | 2,967 / 3,536 / 3,393 / 3,275 / 3,362 | 3,037 / 3,591 / 3,465 / 3,333 / 3,251 | 2,866 / 3,413 / 3,244 / 3,150 / 3,165 |
| pl / tr | 3,240 / 2,819 | 3,341 / 2,941 | 3,045 / 2,525 |
| zh-hans | 2,555 (52%) | 2,653 (54%) | 2,380 (48%) |
| zh-hant | 449 (12%) | 465 (12%) | 436 (12%) |
| units in all 10 | 109 | 136 | 92 |

The Simplified edition aligns like any other language; the Traditional one aligns at 12% for all three models with identical agreement patterns, so the loss is upstream: the Taiwan edition is typeset vertically and the OCR emits lines in the wrong order. Script handling (Hans vs Hant) is not the problem. Fix belongs in the OCR stage (page rotation / vertical-text mode), not in the embedder.

### Thirteen-language test: McLuhan, *Understanding Media* (2026-09-10)

The collection now holds 13 editions (de, en, es, fr, hr, it, lt, nl, pl, pt, ru, sr, zh). All three models, centred, threshold 1.05:

| | jina | gemma | granite |
|---|---|---|---|
| total links, 12 targets | 54,349 | 55,128 | 51,994 |
| Lithuanian yield | 53% | 42% | 56% |
| Croatian / Serbian yield | 66% / 61% | 65% / 62% | 66% / 62% |
| units in all 13 editions | 422 | 325 | 346 |
| units in 10+ editions | 2,971 | 3,120 | 2,652 |
| embed 172k texts | (cached) | 1,024 s | 1,088 s |

Same pattern as King: gemma edges the totals through the big languages, jina holds every language and wins the all-language units by 20-30%. Final choice for the collection: **jina**.

### Issue 106

- `min_langs` defaults to 2: a unit is written when the pivot sentence aligns in at least one other edition, so en A B C / de A B C / fr A C gives A(en,de,fr), B(en,de), C(en,de,fr).
- No hidden folders: `<lang>/<stem>.md` and `<stem>.norm.md` next to the source; diskcache and scratch in `<book>/paraltext-cache/`.
- DjVu: `djvutxt` text layer (the one DjVu in the collection, Lakoff ru, converts in 0.24 s); scans are rendered with `ddjvu` and OCRed with docling.
- Granite facts (GGUF metadata, model card, pricing) in the renamed `JINA-VS-GEMMA-VS-GRANITE.md`.

### Tests

`uv run pytest`: 51 passed, 89% coverage. `ruff check` and `ty check src/` clean.

### Batch run over the collection (2026-09-10)

`vexy-paraltext batch ebook-font-l10n --config batch.toml` (normalize off, jina, centred, `min_langs = 2`), log in `batch2.log`. First attempt died silently at book 6 inside docling (segfault on the Ogilvy on Advertising English scan); OCR now runs in a child process and a segfault only skips that edition. Fixes landed while it ran, so these books get a rerun afterwards: ellen-lupton--thinking-with-type (markit rejected the Spanish PDF's CJK CMap; PyMuPDF fallback added) and every book with an image-only EPUB (Munari it, Lakoff pl, Smeijers en+zh, Noordzij es+it, Zapf es, Hochuli en+it, Elam Grid Systems en, Bringhurst pt, Wong es: page images are now stacked into a PDF and OCRed). Known skip: Ogilvy on Advertising en (docling segfault).

Low-yield books diagnosed after the run: Noordzij pt (markit kept 5 KB of an 85 KB text layer; now falls back to PyMuPDF when markit keeps under half the raw text) and fr (the "edition" is a 3-page excerpt, nothing to fix); Tschichold, Form of the Book ru (text layer is cp1251 bytes mislabelled as Latin-1; `convert.fix_mojibake` recodes Cyrillic-language editions); Elam, Geometry of Design pt (EPUB with letter-spaced words, "m a r a v i l h a", which only the LLM normalize stage repairs); Haarmann de (1.6k sentences against 5-7k for es/it: the German edition is shorter, not broken). Rerun #2 after the image-EPUB rerun: Noordzij, Tschichold Form of the Book. Munari: the Italian EPUB is *Artista e designer* (1971), a different book from *Design as Art* (*Arte come mestiere*), so its 33 units are the ceiling; a catalogue error, not a pipeline one.

### Collection result (2026-09-10 12:23)

37 of 40 books have a TMX, 131,115 translation units in total (`min_langs = 2`, jina, centred, normalize off).

| book | units | languages in TMX |
|---|---|---|
| adrian-frutiger--signs-and-symbols | 3,459 | de en es fr |
| adrian-frutiger--typefaces-the-complete-works | 9,455 | de en fr |
| alberto-manguel--a-history-of-reading | 5,357 | en es fr it pl pt ro tr zh-hans zh-hant |
| bruno-munari--design-as-art | 33 | en it |
| david-crystal--the-cambridge-encyclopedia-of-language | 9,570 | de en zh |
| david-ogilvy--confessions-of-an-advertising-man | 1,671 | pt ru zh |
| david-ogilvy--ogilvy-on-advertising | 3,471 | fr ro ru zh |
| elizabeth-eisenstein--the-printing-press-as-an-agent-of-change | 5,090 | en it pt tr zh |
| ellen-lupton--thinking-with-type | 409 | en es pt |
| eric-gill--an-essay-on-typography | 326 | en it |
| fred-smeijers--counterpunch | 747 | en zh |
| george-lakoff-mark-johnson--metaphors-we-live-by | 6,196 | ar cs de en es fr it pl ru tr zh |
| gerrit-noordzij--the-stroke | 627 | en es fr it pt |
| harald-haarmann--universal-history-of-writing | 148 | de es it |
| henestrosa-meseguer-scaglione--como-crear-tipografias | 314 | en es zh |
| hermann-zapf--alphabet-stories | 77 | es ru |
| jacques-derrida--of-grammatology | 7,635 | en fr it pt ru tr zh |
| james-felici--the-complete-manual-of-typography | 5,013 | en pl ru zh |
| jan-tschichold--the-form-of-the-book | 1,020 | en ru |
| jan-tschichold--the-new-typography | 2,036 | en es fr ru |
| johannes-itten--the-art-of-color | 2,641 | en es ru zh |
| josef-muller-brockmann--grid-systems-in-graphic-design | 644 | es ru zh |
| jost-hochuli--detail-in-typography | 576 | en es it pl zh |
| kimberly-elam--geometry-of-design | 179 | en pt |
| kimberly-elam--grid-systems | 413 | en es |
| lucien-febvre-henri-jean-martin--the-coming-of-the-book | 5,619 | en fr pt zh |
| marshall-mcluhan--the-gutenberg-galaxy | 6,470 | en es it pt ru tr |
| marshall-mcluhan--understanding-media | 9,908 | de en es fr hr it lt nl pl pt ru sr zh |
| massimo-vignelli--the-vignelli-canon | 343 | en zh |
| otl-aicher--die-welt-als-entwurf | 4,330 | de en pl |
| robert-bringhurst--the-elements-of-typographic-style | 6,049 | en it pl pt ru |
| simon-garfield--just-my-type | 3,998 | en es fr it pt sv tr zh |
| stephen-king--on-writing | 6,536 | cs da de en es hu it lt pl pt ro ru sv tr zh |
| umberto-eco--a-theory-of-semiotics | 3,818 | de en es fr it |
| walter-j-ong--orality-and-literacy | 3,850 | de en es it pt tr |
| wucius-wong--principles-of-form-and-design | 814 | en es |
| yannis-haralambous--fonts-and-encoding | 12,273 | en fr |

No TMX: emil-ruder--typographie, hans-peter-willberg-friedrich-forssman--erste-hilfe-in-typografie, heiko-hortsch--erfreuliche-drucksachen-durch-gute-typografie, hermann-zapf--manuale-typographicum (single editions or single multilingual volumes; the latter need the language-split item in PLAN.md).

### Low-yield books: best of three models (2026-09-10)

The six books under 25% yield were re-aligned with all three models (`candidate-*.tmx`) and the largest TMX kept. Gains are 5-14%: the low yield is in the data (illustrated books, short or mismatched editions), not the model.

| book | jina units | kept |
|---|---|---|
| ellen-lupton--thinking-with-type | 409 | 441 (gemma) |
| harald-haarmann--universal-history-of-writing | 148 | 163 (granite) |
| henestrosa-meseguer-scaglione--como-crear-tipografias | 314 | 327 (gemma) |
| josef-muller-brockmann--grid-systems-in-graphic-design | 644 | 705 (gemma) |
| wucius-wong--principles-of-form-and-design | 814 | 848 (gemma) |
| kimberly-elam--geometry-of-design | 179 | 204 (gemma) |

All other books keep their jina TMX. Final count: 37 of 40 books with a TMX; the remaining three plus Hortsch are single editions or single multilingual volumes.


### Issue 301 closure

Shared uubed integration passed the final workspace runner: this consumer has
112 passing tests, 93.49% coverage, source/test ruff and production-source ty clean.
Real copied FontExplorer EPUB-to-TMX output contains 63 units at both precisions,
62 identical and one changed alignment. Independent issue review scored 94/100.
The consumer uv.lock is current; the absolute editable source path and optional
MLX dependency are documented. Private test results remain in the uubed workspace.

## Release and privacy cleanup

Implemented standalone tag-derived release commands, source/archive privacy gates, fresh artifact manifests, dry runs and same-tag retries. Verification is recorded in the workspace release report. Existing local data remains on disk.

### Release verification — 2026-09-12

113 tests passed; Ruff and ty passed; v1.0.1 wheel/sdist preview verified. Home-relative model paths have a regression test. Shared release-flow suite: 11 passed. Source HEAD and latest tag remained unchanged. No live publication was performed.

## 2026-09-12 — License-file release validation

The shared archive gate now checks every License-File declaration in metadata
2.4+ against a regular file at the required sdist or wheel location. Missing,
misplaced and directory-only licenses fail before pushing or uploading. Synced
the helper across all six repositories. Verification: 14 release-tool tests
passed; nine existing sibling preview artifacts passed the stronger checks.
