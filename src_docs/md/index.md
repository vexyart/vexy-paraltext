# vexy-paraltext

`vexy-paraltext` turns a folder of translated editions of one book into a single TMX translation memory of aligned sentences. You give it the English PDF, the German EPUB and the French DjVu of the same book. It gives you back `book.tmx`, where each translation unit holds one sentence and its counterparts in the other editions.

The tool runs locally. Text extraction uses command-line converters, sentence vectors come from local GGUF embedding models run through llama.cpp, and an optional clean-up pass talks to a local LLM served by LM Studio.

## What goes in, what comes out

A book folder holds one subfolder per language, named with the language code. Each subfolder holds one edition:

```text
book/
  en/Book.pdf
  de/Buch.epub
  fr/Livre.djvu
```

After `vexy-paraltext run book`, the folder looks like this:

```text
book/
  en/Book.pdf
  en/Book.md            stage 1: converter markdown, next to the source
  en/Book.norm.md       stage 2: LLM-normalized text (only when normalize is enabled)
  de/...
  fr/...
  paraltext-cache/      diskcache of LLM chunks and sentence vectors, converter scratch
  book.tmx              stage 4: the translation memory
```

The TMX file is named after the book folder: `book/` produces `book/book.tmx`.

## Which sentences end up in the TMX

One edition is the pivot (English by default). A translation unit is written when a pivot sentence aligns in at least `min_langs` editions, counting the pivot itself. The default is `min_langs = 2`.

Follow one example through. The English edition has sentences A, B and C. The German edition has A, B and C. The French edition has only A and C. With the default setting, the TMX contains:

- A in English, German and French
- B in English and German
- C in English, German and French

Sentences with no counterpart in any other edition are dropped. Units are never padded with empty segments. Raise `min_langs` to require more editions per unit.

## The four stages

| stage | command | input | output |
|---|---|---|---|
| 1. Convert | `convert` | PDF, EPUB or DjVu | `<lang>/<stem>.md` |
| 2. Normalize | `normalize` | `<stem>.md` | `<lang>/<stem>.norm.md` |
| 3. Embed | `embed` | sentences of each edition | vectors in `paraltext-cache/` |
| 4. Align | `align` | vectors of all editions | `<book>.tmx` |

`run` chains all four. Each stage reuses what the previous run left on disk, so a second run only redoes work whose inputs changed. See [How it works](how-it-works.md) for what happens inside each stage.

## Where to go next

- [Installation](installation.md): the package and the external converters.
- [Quickstart](quickstart.md): build your first TMX.
- [Command line](cli.md): every command and option.
- [Configuration](configuration.md): the `paraltext.toml` file.
- [Embedding models](models.md): which model to choose and why.
- [TMX output](output.md): the file format the tool writes.
- [Troubleshooting](troubleshooting.md): common failures and their fixes.
- [Development](development.md): tests, builds and releases.
