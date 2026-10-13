# Development

## Set up

```bash
git clone https://github.com/vexyart/vexy-paraltext.git
cd vexy-paraltext
uv sync --all-groups
```

Dependency groups: `test` (pytest, pytest-cov), `lint` (ruff, ty) and `ocr` (docling).

## Tests and checks

```bash
./test.sh
```

`test.sh` creates `.venv` with the `test` and `lint` groups if needed, installs the package in editable mode, and runs, in order:

1. `pytest`, with a coverage floor of 80% (`--cov-fail-under=80`).
2. `ruff check src tests`.
3. `ty check src`.

The tests build synthetic books in temporary folders and use a stub embedder, so they need no GGUF model, no converter and no chat server. The two OCR tests in `tests/test_convert.py` need docling importable; install the `ocr` group to run them.

Run a single file while working:

```bash
uv run pytest tests/test_align.py
```

## Comparison scripts

`scripts/` holds the scripts used for the measurements in [Embedding models](models.md):

```bash
uv run scripts/compare_lakoff.py BOOK 0 1.05 jina,gemma,granite   # per-language yield, agreement, multi-way units
uv run scripts/compare_models.py BOOK 2000                        # jina vs gemma on a slice, with sample disagreements
```

`scripts/bake_pdf.py` timed the PDF converters for the bake-off that chose `markit`.

## Code layout

| module | role |
|---|---|
| `cli.py` | The `Cli` class that Fire turns into commands. |
| `config.py` | Dataclasses for `paraltext.toml` and the config file search. |
| `pipeline.py` | `Book`, the four stages and `run_all`. |
| `convert.py` | PDF, EPUB and DjVu to markdown. |
| `ocr.py` | docling OCR, run as a child process. |
| `normalize.py` | Chunking and the chat-completion client. |
| `segment.py` | Markdown clean-up and sentence splitting. |
| `embed.py` | Adapter to the `uubed` embedding engine. |
| `cache.py` | diskcache stores for normalized chunks and vectors. |
| `align.py` | Centring, margin mining, overlap resolution, order filter, gap filling. |
| `tmx.py` | TMX writer. |

## Versions

The version comes from Git tags through hatch-vcs. A build writes `src/vexy_paraltext/_version.py`, which is ignored by Git. Without it, `vexy_paraltext.__version__` is `0.0.0.dev0`.

## Build

```bash
./build.sh            # documentation and package
./build.sh docs       # documentation only: src_docs/md -> docs/
./build.sh package    # package only: dist/*.whl and dist/*.tar.gz, checked with twine
```

The package build uses `uv build --no-sources`, so local editable source paths never leak into release metadata.

## Documentation

The documentation sources are Markdown files in `src_docs/md/`. ProperDocs with the MaterialX theme builds them into `docs/`, which GitHub Pages serves at <https://vexy.dev/vexy-paraltext/>.

```bash
src_docs/build.sh         # strict build into docs/
src_docs/build.sh serve   # live preview on http://127.0.0.1:8000
```

Do not edit `docs/` by hand; the next build replaces it. The `Docs` workflow rebuilds `docs/` and commits it on every push to `main` that changes `src_docs/`.

## Release

Prerequisites: review `git status` and `git diff`, because the release commits every pending change; push access to `origin`, and a PyPI credential for `uv publish`, such as `UV_PUBLISH_TOKEN` in the environment.

1. Run the tests:

    ```bash
    ./test.sh
    ```

2. Publish:

    ```bash
    ./publish.sh
    ```

    `gitnextver` commits all pending changes, tags the next `vX.Y.Z` and pushes. The script then builds the package from that tag with `./build.sh package` and uploads `dist/*` with `uv publish`.

`publish.sh` stops if `HEAD` carries no `vX.Y.Z` tag afterwards; `gitnextver` only tags when there is something to commit.

The older gated release helper, `scripts/release.py`, is still in the repository. It runs the tests, builds in a disposable copy, verifies archive contents and supports `--dry-run`, `--resume vX.Y.Z` and `--bump`. Run it with `uv run --no-project --script scripts/release.py --dry-run`. See `RELEASING.md`.
