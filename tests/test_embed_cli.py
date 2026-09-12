# this_file: tests/test_embed_cli.py
"""Embedder plumbing and CLI wiring (no GGUF needed)."""

from pathlib import Path

import numpy as np
import pytest
from uubed.embeddings import Embedder as SharedEmbedder

from vexy_paraltext import cli
from vexy_paraltext.cache import EmbeddingCache
from vexy_paraltext.config import EmbedConfig, ModelSpec
from vexy_paraltext.embed import MODELS, Embedder


def test_from_alias_when_known_then_prefix_set():
    e = Embedder.from_alias("jina")
    assert e.path == MODELS["jina"][0]
    assert e.prefix.startswith("Query")


def test_from_alias_when_known_path_then_preserves_profile(tmp_path: Path):
    path = tmp_path / "custom.gguf"
    path.write_bytes(b"weights")
    spec = ModelSpec(path=str(path), model="gemma", prefix="similarity: ")
    e = Embedder.from_alias(str(path), models={"custom": spec})
    assert e.spec.model == "gemma"
    assert e.prefix == "similarity: "


def test_from_alias_when_unknown_path_then_requests_explicit_profile(tmp_path: Path):
    path = tmp_path / "unknown.gguf"
    path.write_bytes(b"weights")
    with pytest.raises(ValueError, match="model profile"):
        Embedder.from_alias(str(path))


def test_embed_when_model_missing_then_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        Embedder("x", tmp_path / "none.gguf", "").embed(["a"])


def test_embed_cached_when_second_call_then_reads_npz(tmp_path: Path, monkeypatch):
    calls = []

    def fake(self, texts):
        calls.append(len(texts))
        return np.ones((len(texts), 4), dtype=np.float32)

    monkeypatch.setattr(Embedder, "embed", fake)
    weights = tmp_path / "m.gguf"
    weights.write_bytes(b"test weights")
    e = Embedder("jina", weights, "")
    cache = EmbeddingCache(tmp_path / "c")
    a = e.embed_cached(["x", "y"], cache)
    b = e.embed_cached(["x", "y", "z"], cache)
    assert calls == [2, 1], "second call embeds only the unseen text"
    assert np.array_equal(a, b[:2])
    assert b.shape == (3, 4)


def test_embed_when_shared_engine_then_delegates_with_config(tmp_path, monkeypatch):
    weights = tmp_path / "jina.gguf"
    weights.write_bytes(b"weights")
    seen = []

    def fake(self, texts):
        seen.append((self.dimensions, self.precision, self.prefix))
        return np.ones((len(texts), self.dimensions), dtype=np.float32)

    monkeypatch.setattr(SharedEmbedder, "embed", fake)
    embedder = Embedder("jina", weights, "Query: ", options=EmbedConfig(dimensions=128, precision="int4"))
    assert embedder.embed(["sentence"]).shape == (1, 128)
    assert seen == [(128, "int4", "Query: ")]


def test_cache_identity_when_prefix_changes_then_reembed(tmp_path, monkeypatch):
    weights = tmp_path / "jina.gguf"
    weights.write_bytes(b"weights")
    calls = []

    def fake(self, texts):
        calls.append(self.prefix)
        return np.ones((len(texts), 32), dtype=np.float32)

    monkeypatch.setattr(Embedder, "embed", fake)
    cache = EmbeddingCache(tmp_path / "cache")
    Embedder("jina", weights, "Document: ").embed_cached(["same sentence"], cache)
    Embedder("jina", weights, "Query: ").embed_cached(["same sentence"], cache)
    assert calls == ["Document: ", "Query: "]


def test_cli_run_when_pipeline_stubbed_then_summary(monkeypatch, tmp_path: Path):
    class R:
        units = [1, 2]
        tmx = tmp_path / "o.tmx"

    monkeypatch.setattr(cli.pipeline, "run_all", lambda *a, **k: R())
    assert cli.Cli().run(str(tmp_path)).startswith("2 units")
    monkeypatch.setattr(cli.pipeline, "run_align", lambda *a, **k: R())
    assert cli.Cli().align(str(tmp_path)).startswith("2 units")


def test_cli_batch_when_book_fails_then_continues(monkeypatch, tmp_path: Path, capsys):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    seen = []

    def run_all(book, **k):
        seen.append(book.dir.name)
        if book.dir.name == "a":
            msg = "boom"
            raise ValueError(msg)

        class R:
            units = []
            tmx = book.dir / "x.tmx"

        return R()

    monkeypatch.setattr(cli.pipeline, "run_all", run_all)
    cli.Cli().batch(str(tmp_path))
    assert seen == ["a", "b"]
    assert "0 units" in capsys.readouterr().out


def test_cli_convert_and_embed_when_stubbed_then_paths_listed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli.pipeline, "run_convert", lambda *a, **k: [tmp_path / "en.md"])
    assert cli.Cli().convert(str(tmp_path)).endswith("en.md")
    monkeypatch.setattr(cli.pipeline, "run_normalize", lambda *a, **k: [tmp_path / "en.norm.md"])
    assert cli.Cli().normalize(str(tmp_path)).endswith("en.norm.md")

    class Ed:
        sentences = [1, 2]

    monkeypatch.setattr(cli.pipeline, "run_embed", lambda *a, **k: {"en": Ed()})
    assert cli.Cli().embed(str(tmp_path)) == "en: 2 sentences embedded"


@pytest.mark.parametrize(("command", "stage"), [("embed", "run_embed"), ("align", "run_align"), ("run", "run_all")])
def test_cli_when_embedding_options_then_pipeline_receives_them(tmp_path, monkeypatch, command, stage):
    seen = []

    def capture(book, **kwargs):
        seen.append(book.cfg.embed)
        return {} if command == "embed" else type("Result", (), {"units": [], "tmx": tmp_path / "out.tmx"})()

    monkeypatch.setattr(cli.pipeline, stage, capture)
    getattr(cli.Cli(), command)(str(tmp_path), model="jina", backend="jina", dimensions=256, precision="int4")
    assert seen[0].dimensions == 256
    assert seen[0].precision == "int4"
    assert seen[0].models["jina"].backend == "jina"
    assert seen[0].models["jina"].prefix is None
