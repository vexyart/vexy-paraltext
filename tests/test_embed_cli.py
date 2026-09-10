# this_file: tests/test_embed_cli.py
"""Embedder plumbing and CLI wiring (no GGUF needed)."""

from pathlib import Path

import numpy as np
import pytest

from vexy_paraltext import cli
from vexy_paraltext.cache import EmbeddingCache
from vexy_paraltext.embed import MODELS, Embedder


def test_from_alias_when_known_then_prefix_set():
    e = Embedder.from_alias("jina")
    assert e.path == MODELS["jina"][0]
    assert e.prefix.startswith("Query")


def test_from_alias_when_path_then_no_prefix(tmp_path: Path):
    e = Embedder.from_alias(str(tmp_path / "m.gguf"))
    assert e.name == "m"
    assert e.prefix == ""


def test_embed_when_model_missing_then_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        Embedder("x", tmp_path / "none.gguf", "").embed(["a"])


def test_embed_cached_when_second_call_then_reads_npz(tmp_path: Path, monkeypatch):
    calls = []

    def fake(self, texts):
        calls.append(len(texts))
        return np.ones((len(texts), 4), dtype=np.float32)

    monkeypatch.setattr(Embedder, "embed", fake)
    e = Embedder("stub", tmp_path / "m.gguf", "")
    cache = EmbeddingCache(tmp_path / "c")
    a = e.embed_cached(["x", "y"], cache)
    b = e.embed_cached(["x", "y", "z"], cache)
    assert calls == [2, 1], "second call embeds only the unseen text"
    assert np.array_equal(a, b[:2])
    assert b.shape == (3, 4)


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
