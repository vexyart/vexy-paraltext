# this_file: src/vexy_paraltext/convert.py
"""Convert one book edition (EPUB or PDF) to a single markdown file.

Backends (chosen in the bake-off recorded in WORK.md):
- PDF with a text layer: ``markit`` (npm ``@shiftlabs/markit``): column-aware, ~2 s per 470-page book.
- PDF without a text layer: ``docling`` with OCR (optional ``ocr`` dependency group).
- EPUB: ``epub2md.py`` (path from ``VEXY_EPUB2MD``, default ``~/bin/epub2md.py``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from loguru import logger

SUFFIXES = (".pdf", ".epub", ".djvu")
_MIN_CHARS_PER_PAGE = 200
_MIN_TEXT_PAGE_FRACTION = 0.3
_MIN_MEAN_CHARS_PER_PAGE = 400  # below this a "text layer" is captions over scanned pages
_MARKIT_MIN_FRACTION = 0.5  # markit output shorter than this share of the raw text layer means it dropped text
_MIN_EPUB_CHARS = 2000


class ConvertError(RuntimeError):
    """A converter is missing or failed."""


def find_source(lang_dir: Path) -> Path:
    """Return the single EPUB or PDF inside a language folder."""
    files = sorted(p for p in lang_dir.iterdir() if p.suffix.lower() in SUFFIXES)
    if not files:
        msg = f"no .pdf or .epub in {lang_dir}"
        raise ConvertError(msg)
    if len(files) > 1:
        logger.warning("{} sources in {}, using {}", len(files), lang_dir, files[0].name)
    return files[0]


def has_text_layer(pdf: Path) -> bool:
    """True when enough pages carry extractable text (else the PDF is a scan)."""
    import fitz  # noqa: PLC0415 (heavy import, only needed for PDFs)

    with fitz.open(pdf) as doc:
        lengths = [len(p.get_text()) for p in doc]
    if not lengths:
        return False
    texty = sum(n >= _MIN_CHARS_PER_PAGE for n in lengths)
    return texty >= _MIN_TEXT_PAGE_FRACTION * len(lengths) and sum(lengths) / len(lengths) >= _MIN_MEAN_CHARS_PER_PAGE


def needs_ocr(lang_dir: Path) -> bool:
    """True for a PDF without a text layer whose markdown does not exist yet (DjVu is checked at run time)."""
    try:
        src = find_source(lang_dir)
    except ConvertError:
        return False
    if src.with_suffix(".md").exists() or src.stat().st_size == 0:
        return False
    suffix = src.suffix.lower()
    if suffix == ".pdf":
        return not has_text_layer(src)
    if suffix == ".epub":
        return epub_is_image_only(src)
    return False


def epub_is_image_only(epub: Path) -> bool:
    """True when the EPUB carries page images but no (or only cover-sized) HTML content."""
    try:
        with zipfile.ZipFile(epub) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        return False
    html_bytes = sum(i.file_size for i in infos if i.filename.lower().endswith((".html", ".xhtml", ".htm")))
    images = sum(i.filename.lower().endswith(_IMAGE_SUFFIXES) for i in infos)
    return images >= _MIN_IMAGE_PAGES and html_bytes < _MIN_EPUB_CHARS * images


_CYRILLIC_LANGS = {"ru", "uk", "bg", "sr", "mk", "be"}
_LATIN1_HIGH = re.compile(r"[\u00c0-\u00ff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


def fix_mojibake(text: str, lang: str) -> str:
    """Undo cp1251-as-Latin-1 text layers (Cyrillic PDFs whose fonts carry no Unicode map)."""
    if lang.split("-", maxsplit=1)[0] not in _CYRILLIC_LANGS:
        return text
    if len(_CYRILLIC.findall(text)) > len(text) * 0.05 or len(_LATIN1_HIGH.findall(text)) < len(text) * 0.2:
        return text
    try:
        fixed = text.encode("latin-1", errors="ignore").decode("cp1251", errors="ignore")
    except UnicodeError:
        return text
    logger.warning("recoded cp1251 mojibake text layer for {}", lang)
    return fixed


def pymupdf_text(pdf: Path) -> str:
    """Plain text-layer extraction, one paragraph per text block; fallback when markit rejects a PDF (e.g. CJK CMaps)."""
    import fitz  # noqa: PLC0415

    blocks: list[str] = []
    with fitz.open(pdf) as doc:
        for page in doc:
            for b in page.get_text("blocks"):
                text = " ".join(str(b[4]).split())
                if text:
                    blocks.append(text)
    return "\n\n".join(blocks) + "\n"


def _run(cmd: list[str]) -> str:
    logger.debug("run: {}", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if proc.returncode != 0:
        msg = f"{cmd[0]} failed ({proc.returncode}): {proc.stderr.strip()[:500]}"
        raise ConvertError(msg)
    return proc.stdout


def djvu_to_markdown(djvu: Path, workdir: Path) -> str:
    """DjVu: use the embedded text layer (djvutxt); without one, render to PDF (ddjvu) and OCR it with docling."""
    if not shutil.which("djvutxt"):
        msg = "djvutxt not found; install with: brew install djvulibre"
        raise ConvertError(msg)
    text = _run(["djvutxt", str(djvu)])
    if len(text.strip()) >= _MIN_EPUB_CHARS:
        return _djvu_text_to_markdown(text)
    logger.info("{} has no DjVu text layer, rendering to PDF for OCR (slow)", djvu.name)
    workdir.mkdir(parents=True, exist_ok=True)
    pdf = workdir / (djvu.stem + ".pdf")
    _run(["ddjvu", "-format=pdf", "-quality=85", str(djvu), str(pdf)])
    return ocr_pdf_isolated(pdf)


def _djvu_text_to_markdown(text: str) -> str:
    """djvutxt separates pages with form feeds and lines with newlines; rebuild paragraphs from blank lines."""
    pages = text.split("\f")
    return "\n\n".join(p.strip() for p in pages if p.strip())


def ocr_pdf_isolated(pdf: Path) -> str:
    """Run docling in a child process; a crash there becomes a ConvertError here instead of killing the batch."""
    try:
        import docling  # noqa: F401, PLC0415
    except ImportError as exc:
        msg = "scanned PDF needs docling: uv sync --group ocr"
        raise ConvertError(msg) from exc
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ocr.md"
        proc = subprocess.run([sys.executable, "-m", "vexy_paraltext.ocr", str(pdf), str(out)], capture_output=True, text=True, check=False)  # noqa: S603
        if proc.returncode != 0 or not out.exists():
            tail = proc.stderr.strip().splitlines()[-3:]
            msg = f"OCR of {pdf.name} failed (exit {proc.returncode}): {' | '.join(tail)[:400]}"
            raise ConvertError(msg)
        return out.read_text(encoding="utf-8")


def pdf_to_markdown(pdf: Path) -> str:
    """Convert a text-layer PDF with markit (fast) or a scanned PDF with docling OCR."""
    if has_text_layer(pdf):
        markit = shutil.which("markit")
        if not markit:
            msg = "markit not found; install with: npm install -g @shiftlabs/markit"
            raise ConvertError(msg)
        try:
            md = _run([markit, "-q", "--no-images", str(pdf)])
        except ConvertError as exc:
            logger.warning("markit failed on {} ({}); falling back to PyMuPDF text extraction", pdf.name, str(exc)[-120:])
            return pymupdf_text(pdf)
        plain = pymupdf_text(pdf)
        if len(md) < _MARKIT_MIN_FRACTION * len(plain):
            logger.warning("markit kept {} of {} chars of {}; using PyMuPDF text instead", len(md), len(plain), pdf.name)
            return plain
        return md
    logger.info("{} has no text layer, running docling OCR (slow)", pdf.name)
    return ocr_pdf_isolated(pdf)


def epub_to_markdown(epub: Path, workdir: Path, epub2md: str = "~/bin/epub2md.py") -> str:
    """Convert an EPUB via the external epub2md.py script (merged into one file)."""
    script = Path(os.environ.get("VEXY_EPUB2MD", epub2md)).expanduser()
    if not script.exists():
        msg = f"epub2md.py not found at {script}; set VEXY_EPUB2MD"
        raise ConvertError(msg)
    workdir.mkdir(parents=True, exist_ok=True)
    _run(["uv", "run", "-s", str(script), str(epub), "--output_dir", str(workdir), "--merge", "--force"])
    mds = sorted(workdir.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
    if mds and mds[0].stat().st_size >= _MIN_EPUB_CHARS:
        return mds[0].read_text(encoding="utf-8")
    pdf = workdir / (epub.stem + ".pdf")
    n_pages = epub_images_to_pdf(epub, pdf)
    if n_pages < _MIN_IMAGE_PAGES:
        msg = f"{epub.name}: EPUB has no usable text and only {n_pages} page images"
        raise ConvertError(msg)
    logger.info("{} is an image-only EPUB ({} pages), running OCR (slow)", epub.name, n_pages)
    return ocr_pdf_isolated(pdf)


_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_MIN_IMAGE_PAGES = 8  # short books ship as a dozen spread images


def epub_images_to_pdf(epub: Path, pdf: Path) -> int:
    """Write the EPUB's page images, in archive order, as one PDF page each; returns the page count."""
    import fitz  # noqa: PLC0415

    doc = fitz.open()
    with zipfile.ZipFile(epub) as zf:
        names = sorted(n for n in zf.namelist() if n.lower().endswith(_IMAGE_SUFFIXES))
        for name in names:
            data = zf.read(name)
            try:
                img = fitz.open(stream=data, filetype=name.rsplit(".", 1)[-1].lower())
                rect = img[0].rect
            except Exception as exc:  # noqa: BLE001  (MuPDF raises its own error classes for undecodable images)
                logger.debug("skipping {} in {}: {}", name, epub.name, exc)
                continue
            page = doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, stream=data)
    if doc.page_count:
        pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(pdf)
    return doc.page_count


def markdown_path(lang_dir: Path) -> Path:
    """``<lang>/<source stem>.md``, next to the PDF/EPUB/DjVu."""
    return find_source(lang_dir).with_suffix(".md")


def convert(lang_dir: Path, work_dir: Path, *, force: bool = False, epub2md: str = "~/bin/epub2md.py") -> Path:
    """Convert the edition in ``lang_dir`` to markdown next to the source file; skip if present."""
    src = find_source(lang_dir)
    out = src.with_suffix(".md")
    if out.exists() and not force:
        logger.debug("cached {}", out)
        return out
    logger.info("converting {}", src.name)
    suffix = src.suffix.lower()
    if suffix == ".epub":
        text = epub_to_markdown(src, work_dir / f"epub-{lang_dir.name}", epub2md)
    elif suffix == ".djvu":
        text = djvu_to_markdown(src, work_dir / f"djvu-{lang_dir.name}")
    else:
        text = fix_mojibake(pdf_to_markdown(src), lang_dir.name)
    out.write_text(text, encoding="utf-8")
    return out
