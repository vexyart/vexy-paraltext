# this_file: tests/test_convert.py
"""Converter plumbing (no external tools)."""

import subprocess
import zipfile
from pathlib import Path

import fitz
import pytest

from vexy_paraltext import convert as cv
from vexy_paraltext import ocr
from vexy_paraltext.convert import ConvertError, convert, find_source, has_text_layer


def _pdf(path: Path, text: str) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(text.splitlines()):
        page.insert_text((72, 72 + 14 * i), line)
    doc.save(path)
    return path


def test_find_source_when_pdf_present_then_returned(tmp_path: Path):
    p = tmp_path / "b.pdf"
    p.write_bytes(b"")
    (tmp_path / "notes.txt").write_text("x")
    assert find_source(tmp_path) == p


def test_find_source_when_nothing_then_error(tmp_path: Path):
    with pytest.raises(ConvertError):
        find_source(tmp_path)


def test_has_text_layer_when_text_pdf_then_true_and_blank_then_false(tmp_path: Path):
    assert has_text_layer(_pdf(tmp_path / "t.pdf", "\n".join(["word " * 10] * 8)))
    assert not has_text_layer(_pdf(tmp_path / "b.pdf", ""))


def test_convert_when_markdown_next_to_source_then_no_conversion(tmp_path: Path):
    lang = tmp_path / "en"
    lang.mkdir()
    (lang / "x.pdf").write_bytes(b"")
    (lang / "x.md").write_text("cached")
    assert convert(lang, tmp_path / "work").read_text() == "cached"
    assert cv.markdown_path(lang) == lang / "x.md"


def test_djvu_to_markdown_when_text_layer_then_pages_become_paragraphs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(cv, "_run", lambda cmd: "Page one text " * 200 + "\f" + "Page two text " * 200)
    md = cv.djvu_to_markdown(tmp_path / "b.djvu", tmp_path / "work")
    assert md.count("\n\n") == 1
    assert md.startswith("Page one")


def test_djvu_to_markdown_when_no_text_then_rendered_and_ocred(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd):
        calls.append(cmd)
        return ""

    monkeypatch.setattr(cv.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(cv, "_run", fake_run)
    monkeypatch.setattr(cv, "ocr_pdf_isolated", lambda pdf: f"OCR:{pdf.name}")
    assert cv.djvu_to_markdown(tmp_path / "b.djvu", tmp_path / "work") == "OCR:b.pdf"
    assert calls[1][0] == "ddjvu"


def test_djvu_to_markdown_when_tool_missing_then_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cv.shutil, "which", lambda name: None)
    with pytest.raises(ConvertError, match="djvulibre"):
        cv.djvu_to_markdown(tmp_path / "b.djvu", tmp_path / "work")


def test_epub_to_markdown_when_output_tiny_then_error(tmp_path: Path, monkeypatch):

    script = tmp_path / "epub2md.py"
    script.write_text("")
    work = tmp_path / "work"

    def fake_run(cmd):
        work.mkdir(exist_ok=True)
        (work / "x.md").write_text("# title only")
        return ""

    monkeypatch.setattr(cv, "_run", fake_run)
    monkeypatch.setattr(cv, "epub_images_to_pdf", lambda epub, pdf: 3)  # under _MIN_IMAGE_PAGES
    with pytest.raises(ConvertError, match="no usable text"):
        cv.epub_to_markdown(tmp_path / "b.epub", work, epub2md=str(script))


def _image_epub(path: Path, n: int) -> Path:

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 60), False)  # noqa: FBT003
    pix.clear_with(200)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        for i in range(n):
            zf.writestr(f"OEBPS/images/p{i:03d}.png", pix.tobytes("png"))
    return path


def test_epub_images_to_pdf_when_image_pages_then_one_pdf_page_each(tmp_path: Path):
    epub = _image_epub(tmp_path / "img.epub", 5)
    n = cv.epub_images_to_pdf(epub, tmp_path / "out" / "img.pdf")
    assert n == 5
    with fitz.open(tmp_path / "out" / "img.pdf") as doc:
        assert doc.page_count == 5


def test_epub_to_markdown_when_image_only_then_ocr(tmp_path: Path, monkeypatch):
    epub = _image_epub(tmp_path / "img.epub", 25)
    script = tmp_path / "epub2md.py"
    script.write_text("")
    work = tmp_path / "work"

    def fake_run(cmd):
        work.mkdir(exist_ok=True)
        (work / "x.md").write_text("# title only")
        return ""

    monkeypatch.setattr(cv, "_run", fake_run)
    monkeypatch.setattr(cv, "ocr_pdf_isolated", lambda pdf: f"OCR:{pdf.name}")
    assert cv.epub_to_markdown(epub, work, epub2md=str(script)) == "OCR:img.pdf"


def test_needs_ocr_when_cached_or_epub_or_text_pdf_then_false(tmp_path: Path):
    lang = tmp_path / "en"
    lang.mkdir()
    assert not cv.needs_ocr(lang), "no source at all"
    _pdf(lang / "b.pdf", "")
    assert cv.needs_ocr(lang), "blank pdf needs OCR"
    (lang / "b.md").write_text("cached")
    assert not cv.needs_ocr(lang), "existing markdown wins"


def testocr_pdf_isolated_when_child_dies_then_convert_error(tmp_path: Path, monkeypatch):

    monkeypatch.setattr(cv.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, -9, "", "killed"))
    with pytest.raises(ConvertError, match=r"OCR of b\.pdf failed"):
        cv.ocr_pdf_isolated(tmp_path / "b.pdf")


def testocr_pdf_isolated_when_child_succeeds_then_text_returned(tmp_path: Path, monkeypatch):

    def fake_run(cmd, **k):
        Path(cmd[-1]).write_text("# ocr text")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(cv.subprocess, "run", fake_run)
    assert cv.ocr_pdf_isolated(tmp_path / "b.pdf") == "# ocr text"


def test_ocr_main_when_bad_args_then_usage(capsys):

    assert ocr.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_pdf_to_markdown_when_markit_fails_then_pymupdf_fallback(tmp_path: Path, monkeypatch):
    pdf = _pdf(tmp_path / "t.pdf", "\n".join(["hello world " * 10] * 8))
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/usr/bin/markit")

    def fail(cmd):
        msg = "markit failed (1): unsupported CMap"
        raise ConvertError(msg)

    monkeypatch.setattr(cv, "_run", fail)
    assert "hello world" in cv.pdf_to_markdown(pdf)


def test_fix_mojibake_when_cp1251_as_latin1_then_cyrillic_restored():
    original = "Нельзя применять тире вместо дефиса. " * 5
    broken = original.encode("cp1251").decode("latin-1")
    assert cv.fix_mojibake(broken, "ru") == original
    assert cv.fix_mojibake(original, "ru") == original, "real Cyrillic untouched"
    assert cv.fix_mojibake(broken, "fr") == broken, "only Cyrillic-language editions are recoded"


def test_has_text_layer_when_sparse_captions_over_scans_then_false(tmp_path: Path):
    doc = fitz.open()
    for _ in range(10):
        page = doc.new_page()
        page.insert_text((72, 72), "caption " * 30)  # ~240 chars: passes the per-page test, fails the mean
    doc.save(tmp_path / "s.pdf")
    assert not cv.has_text_layer(tmp_path / "s.pdf")


def test_pdf_to_markdown_when_markit_drops_text_then_pymupdf_used(tmp_path: Path, monkeypatch):
    pdf = _pdf(tmp_path / "t.pdf", "\n".join(["hello world " * 10] * 8))
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/usr/bin/markit")
    monkeypatch.setattr(cv, "_run", lambda cmd: "# title only")
    assert cv.pdf_to_markdown(pdf).count("hello world") >= 70


def test_needs_ocr_when_image_only_epub_then_true(tmp_path: Path):
    lang = tmp_path / "it"
    lang.mkdir()
    _image_epub(lang / "b.epub", 25)
    assert cv.needs_ocr(lang)
    with zipfile.ZipFile(lang / "b.epub", "a") as zf:
        zf.writestr("OEBPS/ch1.xhtml", "<p>" + "real text " * 20000 + "</p>")
    assert not cv.needs_ocr(lang), "an EPUB with substantial HTML is not image-only"


def test_epub_images_to_pdf_when_bad_image_then_skipped(tmp_path: Path):
    epub = _image_epub(tmp_path / "img.epub", 3)
    with zipfile.ZipFile(epub, "a") as zf:
        zf.writestr("OEBPS/images/broken.jpg", b"not an image")
    assert cv.epub_images_to_pdf(epub, tmp_path / "o.pdf") == 3
