# TMX output

The align stage writes a TMX 1.4 file. By default it is `<book_dir>/<book_dir name>.tmx`; `--out` sets another path. An existing file is overwritten.

## Format

The file uses UTF-8, one translation unit per line, and no indentation, so it stays small and diffs line by line:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
<header creationtool="vexy-paraltext" creationtoolversion="0.1" segtype="sentence" o-tmf="md" adminlang="en" srclang="en" datatype="plaintext"/>
<body>
<tu><tuv xml:lang="en"><seg>He works very hard every day.</seg></tuv><tuv xml:lang="de"><seg>Er arbeitet jeden Tag sehr hart.</seg></tuv><tuv xml:lang="fr"><seg>Il travaille très dur chaque jour.</seg></tuv></tu>
</body>
</tmx>
```

| element | content |
|---|---|
| `header/@srclang` | The pivot language. |
| `header/@segtype` | Always `sentence`. |
| `tu` | One aligned pivot span and its counterparts. |
| `tuv/@xml:lang` | The edition's folder name, for example `en`, `de` or `zh-hant`. |
| `seg` | Plain text. |

The pivot `tuv` comes first in each unit. The others follow in the order of the edition folders.

## What a unit contains

- A unit has at least `min_langs` variants (default 2). It never contains empty segments for editions where no translation was found.
- A segment holds one sentence or two adjacent sentences joined by a space. Two-sentence segments appear when one edition splits a sentence that another keeps whole.
- Pairs where the "translation" equals the source text, ignoring case, spaces and punctuation, are left out.

## Text cleaning

Segment text comes from the normalized (or raw) markdown after segmentation, so markdown syntax and HTML tags are already removed. When the file is written:

- `&`, `<` and `>` in text are escaped.
- Attribute values are quoted and escaped.
- Characters that XML 1.0 forbids, such as the control characters U+0000-U+0008, are removed from text and attributes. Tab, line feed, carriage return and all legal Unicode characters, including supplementary-plane ones, are kept.

## Using the file

TMX 1.4 is read by most CAT tools and translation-memory libraries. Because each unit sits on one line, ordinary text tools work too:

```bash
# Count translation units
grep -c '<tu>' book/book.tmx

# Units that include Lithuanian
grep 'xml:lang="lt"' book/book.tmx | wc -l
```
