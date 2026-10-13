# How it works

This page follows one book through the four stages. The code lives in `src/vexy_paraltext/`: `convert.py`, `normalize.py`, `segment.py`, `embed.py`, `align.py`, `tmx.py`, with `pipeline.py` tying them together.

## Finding the editions

The tool lists the subfolders of the book folder in alphabetical order and keeps each one that:

- does not start with a dot, and
- contains at least one `.pdf`, `.epub` or `.djvu` file.

The folder name is the language code. A name made of two or more two-letter codes joined by hyphens, such as `de-en`, marks a single volume in several languages; such folders are skipped with a warning. `zh-hant` is one language and is kept.

A book needs at least two editions; otherwise the stage fails with `need at least two language editions`.

## Stage 1: convert

Each edition becomes one markdown file next to its source: `en/Book.pdf` becomes `en/Book.md`. An existing `.md` is reused unless `--force` is given. Editions with a text layer convert in parallel (`[convert] workers`); editions that need OCR convert one at a time afterwards, because several OCR pipelines side by side ran out of memory.

**PDF.** The tool first checks for a text layer with PyMuPDF. A PDF counts as text when at least 30% of its pages carry 200 or more characters and the mean is at least 400 characters per page.

- With a text layer, `markit -q --no-images` converts it. If `markit` fails, or its output is less than half the length of PyMuPDF's plain text, the tool uses PyMuPDF's text instead, one paragraph per text block.
- Without a text layer, docling OCRs it.

For Cyrillic editions (`ru`, `uk`, `bg`, `sr`, `mk`, `be`), text that looks like cp1251 bytes read as Latin-1 is recoded.

**EPUB.** The external `epub2md.py` script merges the book into one markdown file in the scratch folder `paraltext-cache/epub-<lang>/`. If the largest markdown file it writes is smaller than 2000 bytes, the EPUB is treated as image-only: its page images are stacked into a PDF, one image per page, and OCRed. Fewer than eight usable images is an error.

**DjVu.** `djvutxt` extracts the text layer; form feeds separate pages. If the text is shorter than 2000 characters, `ddjvu -format=pdf -quality=85` renders the file to PDF in `paraltext-cache/djvu-<lang>/` and docling OCRs it.

**OCR.** docling runs in a child process (`python -m vexy_paraltext.ocr <pdf> <out.md>`). If it crashes, that edition fails with a `ConvertError` and the rest of the book continues.

## Stage 2: normalize

When `[normalize] enabled = true`, the markdown is split on blank lines into chunks of at most `chunk_chars` characters. A paragraph longer than that is cut at a space. Chunks go to the chat server in parallel with a fixed system prompt that asks the model to:

- join broken words and stray spaces ("sa me" becomes "same"),
- turn ALL CAPS and letter-spaced headings into sentence case,
- drop page numbers, running heads, tables of contents, figure numbers, footnote markers and markdown syntax,
- keep every sentence, without summarizing or translating.

A failed request is retried three times with 1, 2 and 4 seconds of back-off. An answer cut off by the token limit splits its chunk in two and retries each half, up to three levels deep. Every answer is cached, so an interrupted run resumes where it stopped. The result is `<stem>.norm.md`.

## Stage 3: segment and embed

**Segmentation** (`segment.py`) turns the markdown into sentences:

1. Unescape HTML entities, drop soft hyphens, images, link targets and HTML tags.
2. Rejoin words hyphenated across a line break.
3. Reflow each paragraph onto one line and strip markdown marks (`*`, `_`, `` ` ``, `#`, `>`).
4. Split with `pysbd` for languages it supports; other languages, such as `pt`, `tr`, `ro`, `cs`, `lt`, `hu` and `sv`, use a regex splitter.
5. Keep sentences of 15 to 600 characters where at least half the characters are letters and at most 20% are digits.
6. Drop sentences that occur more than twice in the edition: running heads and table-of-contents entries repeat, body sentences do not.

**Embedding** encodes every sentence and every pair of adjacent sentences. The pairs let one sentence in one edition match two in another. For a 3-sentence edition `[s0, s1, s2]` the tool embeds `s0`, `s1`, `s2`, `s0 s1` and `s1 s2`.

Vectors are looked up in the cache first; only missing texts go to the model. New vectors are stored at the configured `precision`.

## Stage 4: align

Each non-pivot edition is aligned against the pivot, in parallel threads. For one pair of editions:

1. **Centre.** With `center = true`, subtract the mean of all vectors of both editions and renormalize. Without this, a model with a compressed vector space, such as Granite, never clears the margin threshold.
2. **Mine.** For every candidate, find its four nearest neighbours on the other side by cosine similarity. A pair is kept when each side is the other's nearest neighbour and its ratio margin reaches `threshold`. The margin is the pair's cosine divided by the average of both sides' mean similarity to their four neighbours.
3. **Resolve overlaps.** Candidates are taken in descending score order; one that reuses a sentence already taken on either side is dropped.
4. **Keep the book order.** A longest-increasing-subsequence pass keeps the largest set of links that increase on both sides. A translation keeps the source order, so links that jump backwards are dropped.
5. **Fill gaps.** Where exactly one sentence on each side sits unaligned between two links, the two are paired if their cosine is at least `gap_min_cos`.

A link whose target text equals its source text, ignoring spaces, case and punctuation, is dropped. Bilingual editions often quote the original, and those quotes are not translations.

## Building the units

For each pivot span linked in at least `min_langs - 1` other editions, the tool writes one unit containing the pivot text and every linked target text. Spans of two sentences are written as one segment, joined by a space. See [TMX output](output.md) for the file format.
