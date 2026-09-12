---
this_file: DEPENDENCIES.md
---

# Dependencies

| package | why |
|---|---|
| `uubed[inference]` | shared model profiles, persistent local/API inference and portable quantized vector records; editable workspace source during issue 301 development |
| `fire` | CLI from the `Cli` class, no argparse boilerplate |
| `llama-cpp-python` | shared uubed backend runs GGUF embedding models in-process with Metal; no server needed |
| `numpy` | cosine top-k search in blocks, embedding cache (`.npz`) |
| `pysbd` | rule-based sentence splitter for 23 languages, no model download |
| `pymupdf` | text-layer detection (page text length) before choosing a converter |
| `loguru` | logging |
| `diskcache` | SQLite-backed cache for LLM-normalized chunks and per-sentence vectors; chosen over `diskcache_rs` (Rust port, 0.4.x, younger API) because the pure-Python original is mature, transactional and needs no wheel |
| `httpx` | chat-completion calls to LM Studio's OpenAI-compatible endpoint; sync client, thread pool for concurrency |

Dependency groups: `lint` (ruff, ty), `test` (pytest, pytest-cov), `ocr` (docling: slow OCR path for scanned PDFs only).

External tools: `markit` (npm `@shiftlabs/markit`) for PDF to markdown; `~/bin/epub2md.py` for EPUB.

Rejected in the bake-off (see WORK.md): pymupdf4llm (OCRs every image page, 50x slower), liteparse (spatial layout text, columns side by side), anydoc (interleaves columns, no OCR), docling as default (40 min per book), marker (worker crash), mineru (not run: multi-GB model download for a task markit solves in 2 s).


## Issue 301 optional runtimes

The optional `mlx` extra enables uubed's verified MiniLM/Granite MLX runtime.
The shared package also exposes an ONNX CPU extra. Current compatible versions
are documented in the uubed workspace; the consumer lockfile includes updated
shared-package metadata. `[tool.uv.sources].uubed` is an absolute editable path
because this checkout is linked from the workspace; update it after relocation.

## Release tools

uv runs isolated build tools; gitnextver 1.0.1 calculates the next semantic tag; tomlkit preserves Cargo formatting during version synchronization; Hatch VCS generates Python versions; Maturin builds the native Python distribution; Cargo packages/verifies Rust crates; MkDocs builds/deploys the documentation site. These are development/release tools, not new runtime dependencies.
