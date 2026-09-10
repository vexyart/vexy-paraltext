# this_file: tests/test_pipeline.py
"""End-to-end pipeline with a stub embedder (no GGUF needed)."""

from pathlib import Path

import numpy as np
import pytest

from vexy_paraltext import pipeline
from vexy_paraltext.config import Config
from vexy_paraltext.embed import Embedder

EN = ["Adam is a tall man.", "He works very hard every day.", "Type design is a slow craft."]
DE = ["Adam ist ein Mann.", "Er arbeitet jeden Tag sehr hart.", "Schriftgestaltung ist ein langsames Handwerk."]
FR = ["Adam est un homme.", "Il travaille très dur chaque jour.", "Le dessin de caractères est un métier lent."]
_VOCAB = {s: i for i, s in enumerate(EN + DE + FR)}


class Stub(Embedder):
    """Deterministic embedder: translations of the same sentence share a direction."""

    def __init__(self) -> None:
        super().__init__("stub", Path("/nonexistent"), "")

    def embed(self, texts: list[str]) -> np.ndarray:
        rng = np.random.default_rng(1)
        base = rng.normal(size=(3, 32))
        out = []
        for t in texts:
            parts = [_VOCAB[p] % 3 for p in _split(t)]
            v = sum(base[i] for i in parts) + 0.01 * rng.normal(size=32)
            out.append(v / np.linalg.norm(v))
        return np.asarray(out, dtype=np.float32)


def _split(text: str) -> list[str]:
    found = [s for s in _VOCAB if s in text]
    return found or [next(iter(_VOCAB))]


def _cfg() -> Config:
    cfg = Config()
    cfg.normalize.enabled = False
    return cfg


@pytest.fixture
def book(tmp_path: Path) -> pipeline.Book:
    for lang, sents in (("en", EN), ("de", DE), ("fr", FR)):
        (tmp_path / lang).mkdir()
        (tmp_path / lang / "book.epub").write_bytes(b"")
        (tmp_path / lang / "book.md").write_text("\n\n".join(sents))
    return pipeline.Book(tmp_path, _cfg())


def test_run_align_when_three_editions_then_tmx_with_all_languages(book: pipeline.Book, monkeypatch):
    monkeypatch.setattr(Embedder, "from_alias", classmethod(lambda cls, alias, models=None: Stub()))
    res = pipeline.run_align(book, model="stub", threshold=1.0)
    assert res.tmx.exists()
    assert res.per_lang == {"de": 3, "en": 3, "fr": 3}
    assert len(res.units) == 3
    assert all(set(u) == {"en", "de", "fr"} for u in res.units)
    assert res.units[0]["de"] == "Adam ist ein Mann."


def test_run_all_when_normalize_disabled_then_convert_then_align(book: pipeline.Book, monkeypatch):
    monkeypatch.setattr(Embedder, "from_alias", classmethod(lambda cls, alias, models=None: Stub()))
    res = pipeline.run_all(book, threshold=1.0)
    assert len(res.units) == 3, "cached markdown is reused, no epub conversion attempted"


def test_run_normalize_when_disabled_then_raw_paths(book: pipeline.Book):
    assert [p.parent.name for p in pipeline.run_normalize(book)] == ["de", "en", "fr"]
    assert all(p.name == "book.md" for p in pipeline.run_normalize(book))


def test_norm_md_when_enabled_then_next_to_source(book: pipeline.Book):
    book.cfg.normalize.enabled = True
    assert book.norm_md("en") == book.dir / "en" / "book.norm.md"


def test_run_align_when_partial_coverage_then_units_with_two_or_more_languages(book: pipeline.Book, monkeypatch):
    (book.dir / "fr" / "book.md").write_text("\n\n".join([FR[0], FR[2]]))  # French lacks sentence B
    monkeypatch.setattr(Embedder, "from_alias", classmethod(lambda cls, alias, models=None: Stub()))
    res = pipeline.run_align(book, model="stub", threshold=1.0)
    langs = [set(u) for u in res.units]
    assert langs == [{"en", "de", "fr"}, {"en", "de"}, {"en", "de", "fr"}], "B is kept as en-de, A and C carry all three"
    strict = pipeline.run_align(book, model="stub", threshold=1.0, min_langs=3)
    assert len(strict.units) == 2


def test_load_edition_when_markdown_missing_then_error(tmp_path: Path):
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "b.pdf").write_bytes(b"")
    (tmp_path / "de").mkdir()
    (tmp_path / "de" / "b.pdf").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="convert"):
        pipeline.load_edition(pipeline.Book(tmp_path, _cfg()), "en")


def test_editions_when_one_edition_then_error(tmp_path: Path):
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "b.pdf").write_bytes(b"")
    with pytest.raises(ValueError, match="two language"):
        pipeline.Book(tmp_path, _cfg()).editions()


def test_editions_when_multilingual_folder_then_skipped(tmp_path: Path):
    for name in ("de-en", "fr", "pl", ".hidden"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "x.pdf").write_bytes(b"")
    assert pipeline.Book(tmp_path, _cfg()).langs() == ["fr", "pl"]


def testis_untranslated_when_same_text_modulo_punctuation_then_true():
    assert pipeline.is_untranslated("His words carry little meaning.", "His words carry little meaning")
    assert pipeline.is_untranslated("You\u2019ll never get it.", "You'll never get it.")
    assert not pipeline.is_untranslated("His words carry little meaning.", "Sus palabras tienen poco significado.")


def test_run_convert_when_scans_present_then_ocr_runs_after_parallel_batch(tmp_path: Path, monkeypatch):
    for lang in ("aa", "bb", "cc"):
        (tmp_path / lang).mkdir()
        (tmp_path / lang / "x.pdf").write_bytes(b"")
    order: list[str] = []
    monkeypatch.setattr(pipeline, "needs_ocr", lambda d: d.name == "aa")

    def fake_convert(d, cache, *, force, epub2md):
        order.append(d.name)
        return cache / f"{d.name}.md"

    monkeypatch.setattr(pipeline, "convert", fake_convert)
    out = pipeline.run_convert(pipeline.Book(tmp_path, _cfg()))
    assert [p.name for p in out] == ["aa.md", "bb.md", "cc.md"], "result order follows edition order"
    assert order[-1] == "aa", "scan converted last, alone"


def test_is_multilingual_folder_when_script_subtag_then_false():
    assert pipeline.is_multilingual_folder("de-en")
    assert pipeline.is_multilingual_folder("de-en-fr")
    assert not pipeline.is_multilingual_folder("zh-hant")
    assert not pipeline.is_multilingual_folder("en")


def test_run_convert_when_one_edition_fails_then_others_continue(tmp_path: Path, monkeypatch):
    for lang in ("aa", "bb"):
        (tmp_path / lang).mkdir()
        (tmp_path / lang / "x.pdf").write_bytes(b"")
    monkeypatch.setattr(pipeline, "needs_ocr", lambda d: False)

    def fake_convert(d, cache, *, force, epub2md):
        if d.name == "aa":
            msg = "image only"
            raise pipeline.ConvertError(msg)
        return d / "x.md"

    monkeypatch.setattr(pipeline, "convert", fake_convert)
    out = pipeline.run_convert(pipeline.Book(tmp_path, _cfg()))
    assert [p.parent.name for p in out] == ["bb"]


def test_converted_langs_when_markdown_missing_then_skipped_or_error(book: pipeline.Book):
    (book.dir / "fr" / "book.md").unlink()
    assert book.converted_langs() == ["de", "en"]
    (book.dir / "de" / "book.md").unlink()
    with pytest.raises(ValueError, match="fewer than two"):
        book.converted_langs()
