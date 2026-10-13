# Troubleshooting

Messages below are quoted from the code. Add `--verbose` to any command to see debug logging, including every converter command line.

## Book-level errors

**`need at least two language editions in <dir>`**
The book folder has fewer than two subfolders with a `.pdf`, `.epub` or `.djvu` file. Check that each language has its own subfolder. Folders named like `de-en` are skipped as multilingual volumes and do not count.

**`fewer than two converted editions in <dir>: run convert first`**
The embed or align stage found markdown for fewer than two editions. Run `convert` (and `normalize` if enabled) and check the log for editions that failed.

**`<path> missing: run convert/normalize first`**
An edition's `.md` or `.norm.md` file is missing. With normalize enabled, the stages read `<stem>.norm.md`; run `normalize`, or set `[normalize] enabled = false`.

## Conversion errors

A failed edition is logged as `<book>/<lang>: <message>` and skipped; the other editions continue.

| message | cause | fix |
|---|---|---|
| `markit not found; install with: npm install -g @shiftlabs/markit` | `markit` is not on `PATH`. | Install it. |
| `djvutxt not found; install with: brew install djvulibre` | djvulibre is missing. | Install it. |
| `scanned PDF needs docling: uv sync --group ocr` | A scan needs OCR and docling is not importable. | Install docling into the tool's environment. |
| `epub2md.py not found at <path>; set VEXY_EPUB2MD` | The EPUB converter script is missing. | Set `VEXY_EPUB2MD` or `[convert] epub2md`. |
| `<file>: EPUB has no usable text and only <n> page images` | The EPUB has neither text nor at least eight page images. | Use another edition. |
| `OCR of <file> failed (exit <code>): ...` | docling crashed in its child process. | Retry; if it repeats, use another edition or convert it by hand (see below). |

### Converting an edition by hand

The convert stage skips any edition whose markdown already exists. To work around a converter, write `<stem>.md` next to the source yourself, for example from another tool's output, and run the remaining stages. Do not pass `--force`, which would overwrite your file.

## Few or poor alignments

- **Low yield for one language.** Check `<stem>.md` for that edition. Scrambled line order, as in vertically typeset text after OCR, cannot be fixed by the aligner. In the tests, a vertically typeset Traditional Chinese edition aligned at 12% while the Simplified Chinese edition of the same translation aligned at about 50%.
- **Mojibake in a Cyrillic PDF.** The tool recodes cp1251 text that was read as Latin-1, but only for folders named `ru`, `uk`, `bg`, `sr`, `mk` or `be`. Name the folder with the right language code.
- **Too many wrong pairs.** Raise `--threshold`, for example to `1.1`. Lowering it to `1.0` admits more caption and footnote mismatches.
- **Too few pairs with Granite.** Make sure `[embed] center` is `true`.
- **English sentences in a non-English edition.** Pairs whose target equals the source text are dropped automatically. Other quoted passages can still align.

## Embedding errors

**`model file missing: <path>`**
The GGUF file of the selected `llama.cpp` profile is not at its configured path. Set `[embed.models.<name>] path`.

**`unknown model alias or missing GGUF: <name>`**
`--model` names neither a profile nor an existing file.

**`GGUF requires a model profile: ...`**
`--model` points at a GGUF file that no profile declares. Add an `[embed.models.<name>]` table with `path` and `model`, then select it by name.

## Normalize errors

**`normalize failed after 3 attempts: ...`**
The chat server did not answer. Check that LM Studio (or another OpenAI-compatible server) is running at `[normalize] base_url` and serves `[normalize] model`. Answers received before the failure are cached; the next run continues from there.

## Starting over

Delete `<book>/paraltext-cache/` to drop cached LLM chunks and vectors. Run `convert --force` and `normalize --force` to rebuild the markdown.
