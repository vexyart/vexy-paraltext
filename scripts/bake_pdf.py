#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# this_file: scripts/bake_pdf.py
"""PDF-to-markdown bake-off runner: ``<venv>/bin/python scripts/bake_pdf.py <tool> <in.pdf> <out.md>``.

Each tool lives in its own throwaway venv (``uv venv``, ``uv pip install <tool>``); results are in WORK.md.
markit and anydoc are npm CLIs and were timed with ``/usr/bin/time`` directly.
"""

import pathlib
import sys
import time

tool, src, dst = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
t = time.time()
if tool == "pymupdf4llm":
    import pymupdf4llm

    md = pymupdf4llm.to_markdown(str(src))
elif tool == "liteparse":
    import liteparse

    r = liteparse.parse(str(src)) if hasattr(liteparse, "parse") else None
    if r is None:
        p = liteparse.LiteParse()
        r = p.parse(str(src))
    md = r.text if hasattr(r, "text") else str(r)
elif tool == "docling":
    from docling.document_converter import DocumentConverter

    md = DocumentConverter().convert(str(src)).document.export_to_markdown()
elif tool == "marker":
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    md = text_from_rendered(PdfConverter(artifact_dict=create_model_dict())(str(src)))[0]
dst.write_text(md)
print(f"{tool} {src.stem} {time.time() - t:.1f}s {len(md)} chars")
