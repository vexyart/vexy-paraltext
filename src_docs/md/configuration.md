# Configuration

Settings live in a TOML file named `paraltext.toml`. Every key is optional; a missing key keeps its built-in default. Command-line options override the file for one call.

## Where the file is found

Without `--config`, the tool checks these locations in order and uses the **first** file it finds. Files are not merged.

1. `<book_dir>/paraltext.toml`
2. `./paraltext.toml` in the current working directory
3. `~/.config/vexy-paraltext/paraltext.toml`

With `--config PATH`, only that file is read. If it does not exist, the defaults apply.

The repository ships an annotated example, `paraltext.example.toml`. Copy it and edit what you need.

!!! warning "`cache_dir` in the example file"
    The example file sets `cache_dir = ".paraltext"`. The built-in default is `paraltext-cache`. If you copy the example unchanged, the cache goes into the hidden folder `<book>/.paraltext/`. Delete that line to keep the default.

## Top-level keys

| key | default | meaning |
|---|---|---|
| `pivot` | none | Source language of the alignment. Without it, `en` is used if present, else the first edition. |
| `min_langs` | `2` | A unit is kept when the pivot sentence aligns in at least this many editions, the pivot included. |
| `cache_dir` | `"paraltext-cache"` | Folder inside the book folder for diskcache data and converter scratch files. |

## `[convert]`

| key | default | meaning |
|---|---|---|
| `epub2md` | `"~/bin/epub2md.py"` | Path of the EPUB converter script. The `VEXY_EPUB2MD` environment variable takes precedence. |
| `workers` | `3` | Editions converted in parallel. Scanned editions that need OCR always run one at a time. |

## `[normalize]`

The normalize stage sends the converter markdown to an OpenAI-compatible chat-completion server, such as LM Studio. It rewrites each chunk into plain paragraphs of complete sentences.

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | `false` skips the stage; later stages read the raw `<stem>.md`. |
| `model` | `"gemma-4-26b-a4b-it-qat-mxfp8"` | Model id as served by the chat server. |
| `base_url` | `"http://localhost:1234/v1"` | Server base URL. Requests go to `<base_url>/chat/completions`. |
| `workers` | `4` | Concurrent requests. |
| `chunk_chars` | `3000` | Maximum characters per chunk. Chunks break on paragraph boundaries. |
| `max_tokens` | `2500` | Maximum tokens per answer. |
| `temperature` | `0.1` | Sampling temperature. |
| `timeout` | `1800.0` | Request timeout in seconds. |

The stage is slow with a large model. With `gemma-4-26b-a4b-it-qat-mxfp8` on an M-series Mac, one illustrated book edition took about two hours; four concurrent requests doubled throughput compared with one, eight did not help further. With `enabled = false` the same book took about five minutes end to end.

## `[embed]`

| key | default | meaning |
|---|---|---|
| `model` | `"jina"` | Profile name from `[embed.models]`, or a GGUF path that a profile declares. |
| `threshold` | `1.05` | Margin-score cutoff for alignment. Higher keeps fewer, cleaner pairs. |
| `gap_min_cos` | `0.6` | Cosine similarity needed to pair a lone sentence between two aligned links. |
| `center` | `true` | Subtract the joint mean vector before mining. Needed for Granite; helps the other models too. |
| `dimensions` | none | Output dimensions. Omit for the model's full size. |
| `precision` | `"int8"` | How vectors are stored in the cache: `float32`, `int8`, `int4` or `binary`. |
| `max_tokens` | `512` | Token limit per text, capped further by each model's context. |
| `batch_tokens` | `4096` | Total llama.cpp batch budget. |
| `batch_size` | `32` | Texts per batch. |

### `[embed.models.<name>]`

Each table declares a model profile that `--model <name>` or `[embed] model` can select. Profiles in the file are added to the built-in ones; a profile with the same name replaces the built-in one completely. Keys you leave out take the defaults below, not the built-in profile's values, so restate `prefix` when you only want to change `path`.

| key | default | meaning |
|---|---|---|
| `path` | `""` | GGUF file, for the `llama.cpp` backend. `~` is expanded. |
| `prefix` | none | Text put in front of every sentence before embedding. |
| `model` | `""` | Model name passed to the uubed engine. Defaults to the profile name. |
| `backend` | `"llama.cpp"` | Inference backend, for example `llama.cpp`, `sentence-transformers`, `mlx`, `jina`, `voyage`, `cloudflare`, `hf` or `openai`. |
| `device` | `"mps"` | Device for local backends. |
| `endpoint` | none | URL for the `openai` backend. |

Built-in profiles:

| name | backend | model file or name |
|---|---|---|
| `jina` | `llama.cpp` | `~/.lmstudio/models/jinaai/jina-embeddings-v5-text-nano-text-matching/v5-nano-text-matching-Q8_0.gguf`, prefix `Query: ` |
| `gemma` | `llama.cpp` | `~/.lmstudio/models/mntcloud/embeddinggemma-300m-Q8_0-better-gguf/embeddinggemma-300M-Q8_0.gguf`, prefix `task: sentence similarity \| query: ` |
| `granite` | `llama.cpp` | `~/.lmstudio/models/mykor/granite-embedding-311m-multilingual-r2-GGUF/granite-embedding-311M-multilingual-r2-Q8_0.gguf`, no prefix |
| `nomic` | `sentence-transformers` | `nomic` |
| `minilm` | `sentence-transformers` | `minilm` |
| `voyage-nano` | `sentence-transformers` | `voyage-nano` |
| `voyage-lite` | `voyage` | `voyage-lite` |

API backends read their keys from the environment, never from the config file. The example file names them: `JINA_API_KEY` for `jina`, `VOYAGE_API_KEY` for `voyage`, `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` for `cloudflare`, `HF_TOKEN` for `hf`.

## Example

A configuration for a collection on an external drive, with German as pivot, three editions per unit and the LLM stage off:

```toml
pivot = "de"
min_langs = 3

[normalize]
enabled = false

[embed]
model = "granite"
threshold = 1.05

[embed.models.granite]
path = "/Volumes/Models/granite-embedding-311M-multilingual-r2-Q8_0.gguf"
prefix = ""
```

## Cache keys

The cache invalidates itself when its inputs change:

- Normalized chunks are keyed by the chat model id, the prompt version and the chunk text.
- Sentence vectors are keyed by the embedding engine's identity, which includes the model and its settings, and by the sentence text. A changed segmentation only embeds the new sentences.
