# this_file: src/vexy_paraltext/ocr.py
"""Docling OCR in a separate process: ``python -m vexy_paraltext.ocr <pdf> <out.md>``.

docling has died silently (no traceback, leaked semaphores) on some scans; isolating it keeps a batch alive.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ocr_pdf(pdf: Path) -> str:
    from docling.document_converter import DocumentConverter  # noqa: PLC0415

    return DocumentConverter().convert(str(pdf)).document.export_to_markdown()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m vexy_paraltext.ocr <pdf> <out.md>", file=sys.stderr)
        return 2
    Path(args[1]).write_text(ocr_pdf(Path(args[0])), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
