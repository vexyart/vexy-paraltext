# this_file: tests/test_config_cache_normalize.py
"""Config loading, disk caches, and the LLM normalizer (HTTP mocked)."""

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

import vexy_paraltext.normalize as nz
from vexy_paraltext.cache import EmbeddingCache, TextCache
from vexy_paraltext.config import Config, NormalizeConfig, load_config
from vexy_paraltext.normalize import Normalizer, chunk_markdown, normalize_file


def test_load_config_when_no_file_then_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config(tmp_path)
    assert cfg.embed.model == "jina"
    assert cfg.normalize.enabled is True
    assert cfg.min_langs == 2
    assert not cfg.cache_dir.startswith(".")
    assert "jina" in cfg.embed.models


def test_load_config_when_file_in_book_dir_then_overrides_and_adds_model(tmp_path: Path):
    (tmp_path / "paraltext.toml").write_text(
        '[embed]\nmodel = "mine"\nthreshold = 1.2\n[embed.models.mine]\npath = "/x.gguf"\nprefix = "Q: "\n[normalize]\nenabled = false\nworkers = 8\npivot = "de"\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.embed.model == "mine"
    assert cfg.embed.threshold == 1.2
    assert cfg.embed.models["mine"].prefix == "Q: "
    assert cfg.embed.models["gemma"].prefix.startswith("task")
    assert cfg.normalize.enabled is False
    assert cfg.normalize.workers == 8


def test_load_config_when_explicit_path_then_used(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('pivot = "fr"\n')
    assert load_config(None, p).pivot == "fr"
    assert isinstance(Config(), Config)


def test_text_cache_roundtrip(tmp_path: Path):
    c = TextCache(tmp_path)
    assert c.get("m", "v1", "in") is None
    c.put("m", "v1", "in", "out")
    assert c.get("m", "v1", "in") == "out"
    assert c.get("m", "v2", "in") is None, "prompt version is part of the key"
    c.close()


def test_embedding_cache_roundtrip(tmp_path: Path):
    c = EmbeddingCache(tmp_path)
    c.store("m", ["a", "b"], np.array([[1, 2], [3, 4]], dtype=np.float32))
    found, missing = c.lookup("m", ["b", "zz", "a"])
    assert missing == [1]
    assert found[0].tolist() == [3, 4]
    assert found[2].tolist() == [1, 2]
    assert c.lookup("other", ["a"])[1] == [0]
    c.close()


def test_chunk_markdown_when_paragraphs_then_grouped_under_limit():
    text = "aaa\n\nbbb\n\n" + "c" * 25 + "\n\nddd"
    chunks = chunk_markdown(text, 10)
    assert chunks[0] == "aaa\n\nbbb"
    assert all(len(c) <= 10 for c in chunks)
    assert "".join(chunks).count("c") == 25, "long paragraph is cut, nothing lost"
    assert chunks[-1] == "ddd"


def test_chunk_markdown_when_empty_then_empty():
    assert chunk_markdown("\n\n  \n", 100) == []


def _fake_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "NORM(" + body["messages"][1]["content"] + ")"}}]})

    return httpx.MockTransport(handler)


def test_normalizer_when_chunk_cached_then_no_http(tmp_path: Path):
    calls: list[str] = []
    cfg = NormalizeConfig(chunk_chars=8, workers=2)
    n = Normalizer(cfg, TextCache(tmp_path))
    n.client = httpx.Client(base_url=cfg.base_url, transport=_fake_transport(calls))
    out = n.normalize("one\n\ntwo\n\nthree")
    assert out == "NORM(one)\n\nNORM(two)\n\nNORM(three)\n"
    assert len(calls) == 3
    assert n.normalize("one\n\ntwo\n\nthree") == out
    assert len(calls) == 3, "second pass served from cache"


def test_normalize_file_when_output_exists_then_skipped(tmp_path: Path):
    src = tmp_path / "en.md"
    src.write_text("x")
    dst = tmp_path / "en.norm.md"
    dst.write_text("done")
    assert normalize_file(src, dst, NormalizeConfig(), TextCache(tmp_path)).read_text() == "done"


def test_normalizer_when_server_flaky_then_retried(tmp_path: Path, monkeypatch):

    monkeypatch.setattr(nz.time, "sleep", lambda s: None)
    n_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n_calls["n"] += 1
        if n_calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    n = Normalizer(NormalizeConfig(), TextCache(tmp_path))
    n.client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))
    assert n.complete("abc") == "ok"
    assert n_calls["n"] == 2


def test_normalizer_when_truncated_then_chunk_split(tmp_path: Path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content)["messages"][1]["content"]
        seen.append(text)
        finish = "length" if len(text) > 10 else "stop"
        return httpx.Response(200, json={"choices": [{"message": {"content": f"N({text})"}, "finish_reason": finish}]})

    n = Normalizer(NormalizeConfig(), TextCache(tmp_path))
    n.client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))
    assert n.complete("aaaa\n\nbbbb\n\ncccc") == "N(aaaa\n\nbbbb)\n\nN(cccc)"
    assert seen[0] == "aaaa\n\nbbbb\n\ncccc"


def test_normalizer_when_always_failing_then_runtime_error(tmp_path: Path, monkeypatch):

    monkeypatch.setattr(nz.time, "sleep", lambda s: None)
    n = Normalizer(NormalizeConfig(), TextCache(tmp_path))
    n.client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(RuntimeError, match="3 attempts"):
        n.complete("x")
