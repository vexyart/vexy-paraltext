# Installation

`vexy-paraltext` is a Python package with a command-line tool. Text extraction depends on a few external programs that you install separately.

## Prerequisites

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) (recommended) or pip.
- For PDFs with a text layer: `markit`, an npm package. Requires Node.js.
- For EPUBs: the `epub2md.py` script (see [EPUB converter](#epub-converter)).
- For DjVu: `djvulibre` (`djvutxt` and `ddjvu`).
- For scanned PDFs and image-only EPUBs: `docling` (optional, slow).
- For embedding: at least one GGUF embedding model on disk (see [Embedding models](models.md)).

## Install the package

From PyPI, as a standalone tool:

```bash
uv tool install vexy-paraltext
vexy-paraltext run --help
```

Or with pip into an existing environment:

```bash
pip install vexy-paraltext
```

From a source checkout, for development:

```bash
git clone https://github.com/vexyart/vexy-paraltext.git
cd vexy-paraltext
uv sync
uv run vexy-paraltext run --help
```

The package depends on `uubed[inference]`, which runs the embedding models, and on `llama-cpp-python`. On Apple Silicon, llama.cpp uses Metal.

### Optional MLX runtime

The `mlx` extra installs uubed's MLX runtime, used by profiles with `backend = "mlx"`:

```bash
uv sync --extra mlx                   # source checkout
uv tool install "vexy-paraltext[mlx]" # standalone tool
```

## Install the converters

1. Install `markit` for PDFs with a text layer:

    ```bash
    npm install -g @shiftlabs/markit
    ```

2. Install `djvulibre` if you have DjVu editions:

    ```bash
    brew install djvulibre
    ```

3. Install `docling` if you have scanned PDFs, scanned DjVu files or image-only EPUBs. In a source checkout, use the `ocr` dependency group:

    ```bash
    uv sync --group ocr
    ```

    For a standalone tool install, add it to the tool environment:

    ```bash
    uv tool install vexy-paraltext --with docling
    ```

    `vexy-paraltext` runs docling in a child process with the same Python interpreter, so docling must be importable from the environment that runs the tool.

When a converter is missing, the conversion of that edition fails with a message that names the install command. Other editions still convert.

## EPUB converter

EPUBs are converted by an external script, `epub2md.py`. The tool looks for it in this order:

1. The `VEXY_EPUB2MD` environment variable.
2. The `[convert] epub2md` key in `paraltext.toml`.
3. The default path `~/bin/epub2md.py`.

The script is run as `uv run -s <script> <epub> --output_dir <dir> --merge --force`, so `uv` must be on `PATH`.

## Check the installation

```bash
vexy-paraltext run --help
which markit djvutxt
```

`vexy-paraltext run --help` prints the arguments and flags of the `run` command. `which` prints the path of each converter that is on `PATH`.
