# Quickstart

This walk-through builds a TMX from three editions of one book. It skips the LLM clean-up stage, which is the fast path: a heavily illustrated 470-page book takes about five minutes end to end.

## Prerequisites

- `vexy-paraltext` and `markit` installed (see [Installation](installation.md)).
- The default embedding model, `jina`, downloaded as a GGUF file. The default path is `~/.lmstudio/models/jinaai/jina-embeddings-v5-text-nano-text-matching/v5-nano-text-matching-Q8_0.gguf`. If yours is elsewhere, set the path in `paraltext.toml` (see [Configuration](configuration.md)).
- Two or more editions of the same book as PDF, EPUB or DjVu.

## Build the TMX

1. Create a book folder with one subfolder per language. Use language codes as folder names:

    ```text
    frutiger/
      en/Typefaces.pdf
      de/Schriften.pdf
      fr/Caracteres.pdf
    ```

    Put exactly one edition in each language folder. If a folder holds several, the tool uses the first in alphabetical order and logs a warning.

2. Create `frutiger/paraltext.toml` that switches off the LLM stage:

    ```toml
    [normalize]
    enabled = false
    ```

3. Run all stages:

    ```bash
    vexy-paraltext run frutiger
    ```

    The tool converts the three PDFs to `en/Typefaces.md`, `de/Schriften.md` and `fr/Caracteres.md`, splits them into sentences, embeds them, aligns German and French against English and writes the TMX. The last line of output names the result:

    ```text
    <number of units> units -> frutiger/frutiger.tmx
    ```

4. Open `frutiger/frutiger.tmx` in a CAT tool or a text editor. Each line between `<body>` and `</body>` is one translation unit.

## Try settings on a slice

Alignment settings are easier to tune on the first part of a book. The vectors stay in the cache, so a second call only redoes the alignment.

1. Align the first 2000 sentences of each edition with a stricter threshold, into a separate file:

    ```bash
    vexy-paraltext align frutiger --limit 2000 --threshold 1.1 --out /tmp/slice.tmx
    ```

2. Compare it with the default threshold:

    ```bash
    vexy-paraltext align frutiger --limit 2000 --out /tmp/slice-default.tmx
    ```

    A higher threshold gives fewer, cleaner pairs. On the Frutiger book, raising it from 1.05 to 1.1 roughly halved the number of units.

## Process a whole collection

`batch` runs `run` on every book folder under a root folder:

```bash
vexy-paraltext batch ~/books
```

A book that fails is logged and skipped; the batch continues with the next one.

## Next steps

- Turn on the LLM clean-up stage for noisier sources: see [Configuration](configuration.md#normalize).
- Compare embedding models: see [Embedding models](models.md).
