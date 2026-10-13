# Embedding models

The aligner compares sentences by their embedding vectors, so the embedding model decides how many translations are found. Three local GGUF models are configured out of the box. All three run through llama.cpp, with Metal on Apple Silicon.

| profile | model | prompt prefix | weights licence |
|---|---|---|---|
| `jina` (default) | jina-embeddings-v5-text-nano, text-matching, Q8_0 | `Query: ` | CC BY-NC |
| `gemma` | EmbeddingGemma 300M, Q8_0 | `task: sentence similarity \| query: ` | see the model card |
| `granite` | granite-embedding-311m-multilingual-r2, Q8_0 | none | Apache 2.0 |

Select a model per call with `--model`, or set `[embed] model` in `paraltext.toml`. Point each profile at the file on your disk with `[embed.models.<name>] path` (see [Configuration](configuration.md#embedmodelsname)).

## Which one to use

The models were compared on whole books from a private collection of translated books: Stephen King's *On Writing* (15 editions), Marshall McLuhan's *Understanding Media* (13), Alberto Manguel's *A History of Reading* (10) and Lakoff and Johnson's *Metaphors We Live By* (6). All runs used English as pivot, threshold 1.05 and centred vectors.

| | `jina` | `gemma` | `granite` |
|---|---|---|---|
| Strengths | Most units that span all editions; never collapses on a language; fastest. | 2-8% more pairs on major Western languages and Chinese. | Most even across languages; best on Czech, Hungarian and Lithuanian; permissive licence. |
| Weaknesses | Non-commercial licence on the weights. | Lithuanian yield of 32-42%; weak on Hungarian. | About 7% fewer pairs overall; slowest. |

Where two models link the same pivot sentence, they pick the same translation 93-100% of the time. The choice of model mostly changes how many sentences are found, not which translation is picked.

Rules of thumb:

- Use `jina` when you want units across many editions, or when the set includes smaller languages.
- Use `gemma` when all editions are in major Western languages or Chinese and recall matters.
- Use `granite` when the weights must carry a permissive licence, or for Baltic and Finno-Ugric languages.

### King, 15 editions

| | `jina` | `gemma` | `granite` |
|---|---|---|---|
| links over 14 target languages | 41,625 | 41,274 | 38,901 |
| best on | da, ro, sv | de, es, it, pl, pt, ru, tr, zh | cs, hu, lt |
| units in all 15 editions | 176 | 98 | 127 |
| units in 10 or more editions | 2,362 | 2,348 | 2,064 |
| embedding 127k texts | 559 s | 608 s | 701 s |

### McLuhan, 13 editions

| | `jina` | `gemma` | `granite` |
|---|---|---|---|
| links over 12 target languages | 54,349 | 55,128 | 51,994 |
| Lithuanian yield | 53% | 42% | 56% |
| units in all 13 editions | 422 | 325 | 346 |
| units in 10 or more editions | 2,971 | 3,120 | 2,652 |

The pattern repeats: `gemma` edges the totals through the large languages, `jina` holds every language and wins the all-edition units by 20-30%.

## Why vectors are centred

Granite's vector space is compressed: random sentence pairs across languages score a cosine of about 0.80 and true translations about 0.97. The best neighbour is then never 5% better than the average neighbour, so the ratio margin never reaches 1.05. On the Lakoff book, Granite found 145 English-Spanish links without centring.

Subtracting the joint mean vector of both editions removes the shared offset. With `[embed] center = true`, the default, Granite found 2,578 English-Spanish links on the same book, and `jina` and `gemma` gained 4-12% as well.

## Other backends

The `uubed` engine also runs profiles with other backends. The example configuration declares local SentenceTransformers and MLX profiles (`nomic`, `minilm`, `voyage-nano`) and API profiles (`jina-api`, `gemma-api`, `granite-api`, `voyage-lite`). The API backends read credentials from environment variables. The comparisons above cover only the three GGUF models.

## Precision and cache size

Vectors are stored in the cache at `[embed] precision`. `int8` is the default. In a test run on one EPUB book, `float32` and `int8` vectors produced 63 units each; 62 were identical and one alignment changed.
