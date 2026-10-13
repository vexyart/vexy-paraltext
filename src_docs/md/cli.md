# Command line

```text
vexy-paraltext COMMAND BOOK_DIR [OPTIONS]
```

The command line is built with [Python Fire](https://github.com/google/python-fire). Options can be written with dashes or underscores (`--min-langs 3` or `--min_langs 3`). Boolean options are switched on by naming them (`--force`, `--verbose`).

Run `vexy-paraltext COMMAND --help` for the generated help of one command.

!!! note "Generated help text"
    Some docstrings behind the generated help predate the current layout. Where they differ from this page, this page follows the code: stage outputs are written next to the sources and into `paraltext-cache/`, not into `.paraltext/`, and `--min-langs` defaults to `2`, not to all editions.

## Commands

| command | does |
|---|---|
| `convert` | Stage 1: converts every edition to markdown. |
| `normalize` | Stage 2: cleans the markdown with a local LLM. |
| `embed` | Stage 3: computes sentence vectors into the cache. |
| `align` | Stage 4: aligns sentences and writes the TMX. |
| `run` | All four stages in order. |
| `batch` | `run` on every book folder under a root folder. |

`align` and `embed` read the output of earlier stages. If the markdown of an edition is missing, they fail with `run convert/normalize first`. `align` runs `embed` itself; vectors already in the cache are reused.

## Options shared by all commands

| option | default | meaning |
|---|---|---|
| `--config PATH` | search order, see [Configuration](configuration.md) | Use this `paraltext.toml` instead of searching for one. |
| `--verbose` | off | Log at debug level (`DEBUG` instead of `INFO`), to stderr. |

## convert

```bash
vexy-paraltext convert BOOK_DIR [--force] [--config PATH] [--verbose]
```

Converts each language folder's PDF, EPUB or DjVu to `<stem>.md` next to the source. Existing markdown is kept unless you pass `--force`. Prints the paths of the markdown files.

An edition that cannot be converted is logged as an error and skipped. The book fails only if fewer than two editions remain at the align stage.

## normalize

```bash
vexy-paraltext normalize BOOK_DIR [--force] [--config PATH] [--verbose]
```

Sends the markdown, chunk by chunk, to an OpenAI-compatible chat server and writes `<stem>.norm.md`. Existing `.norm.md` files are kept unless you pass `--force`. When `[normalize] enabled = false`, the command does nothing and the later stages read the raw `<stem>.md`.

## embed

```bash
vexy-paraltext embed BOOK_DIR [--model NAME] [--limit N]
                     [--backend NAME] [--dimensions N] [--precision NAME]
                     [--config PATH] [--verbose]
```

Splits each edition into sentences and embeds every sentence plus every pair of adjacent sentences. Vectors are stored in `<book>/paraltext-cache/cache/embeddings`. Prints one line per language: `en: 14439 sentences embedded`.

| option | meaning |
|---|---|
| `--model NAME` | A model profile from the config (`jina`, `gemma`, `granite`, ...) or the path of a GGUF file that a profile declares. Default: `[embed] model`, which is `jina`. |
| `--limit N` | Use only the first `N` sentences of each edition. For development. |
| `--backend NAME` | Override the backend of the selected profile, for example `jina` to use the Jina API instead of the local GGUF. For the `jina` and `voyage` backends, the profile's prompt prefix is dropped. |
| `--dimensions N` | Override `[embed] dimensions`. |
| `--precision NAME` | Override `[embed] precision`: `float32`, `int8`, `int4` or `binary`. |

A GGUF path that no profile declares is rejected. Add a profile for it in `paraltext.toml` first (see [Configuration](configuration.md#embedmodelsname)).

## align

```bash
vexy-paraltext align BOOK_DIR [--model NAME] [--pivot LANG] [--threshold X]
                     [--min-langs N] [--limit N] [--out PATH]
                     [--backend NAME] [--dimensions N] [--precision NAME]
                     [--config PATH] [--verbose]
```

Aligns every edition against the pivot and writes the TMX. Prints `<units> units -> <path>`.

| option | default | meaning |
|---|---|---|
| `--pivot LANG` | `pivot` in config, else `en` if present, else the first edition | Source language of the alignment. |
| `--threshold X` | `[embed] threshold` = `1.05` | Margin-score cutoff. Higher keeps fewer, cleaner pairs. |
| `--min-langs N` | `min_langs` = `2` | Keep a unit when at least `N` editions align, the pivot included. |
| `--limit N` | none | Use only the first `N` sentences of each edition. |
| `--out PATH` | `<book_dir>/<book_dir name>.tmx` | Where to write the TMX. |

`--model`, `--backend`, `--dimensions` and `--precision` work as for `embed`.

## run

```bash
vexy-paraltext run BOOK_DIR [all align options] [--force]
```

Runs `convert`, `normalize` and `align` (which embeds). `--force` redoes conversion and normalization; vectors already cached are still reused.

## batch

```bash
vexy-paraltext batch ROOT [--config PATH] [--verbose]
```

Runs `run` on every subfolder of `ROOT` whose name does not start with a dot, in alphabetical order. It prints each book's result line. An exception in one book is logged with the book's folder name and the batch moves on.

`batch` uses the default alignment settings plus whatever the configuration sets. To pass a config to every book, use `--config`; otherwise each book uses its own `paraltext.toml`, if present.

## Examples

```bash
# Everything, with the Gemma model, requiring three editions per unit
vexy-paraltext run mybook --model gemma --min-langs 3

# Re-convert after replacing a PDF
vexy-paraltext convert mybook --force

# German as pivot, output elsewhere
vexy-paraltext align mybook --pivot de --out ~/tm/mybook-de.tmx

# Use a specific config file and debug logging
vexy-paraltext run mybook --config ~/paraltext.toml --verbose
```
