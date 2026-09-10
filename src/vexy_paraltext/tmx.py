# this_file: src/vexy_paraltext/tmx.py
"""Compact TMX 1.4 writer."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

Unit = dict[str, str]

# XML 1.0 Char production: https://www.w3.org/TR/xml/#charsets
_FORBIDDEN_XML = re.compile(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")


def clean_xml_text(text: str) -> str:
    """Remove XML 1.0-forbidden code points from extracted text and metadata."""
    return _FORBIDDEN_XML.sub("", text)


def write_tmx(units: list[Unit], path: Path, *, srclang: str, tool: str = "vexy-paraltext") -> None:
    """Write translation units (lang -> text) as minimal, one-line-per-TU TMX."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tmx version="1.4">',
        f'<header creationtool={quoteattr(clean_xml_text(tool))} creationtoolversion="0.1" segtype="sentence" o-tmf="md" adminlang="en" srclang={quoteattr(clean_xml_text(srclang))} datatype="plaintext"/>',
        "<body>",
    ]
    for unit in units:
        tuvs = "".join(f"<tuv xml:lang={quoteattr(clean_xml_text(lang))}><seg>{escape(clean_xml_text(text))}</seg></tuv>" for lang, text in unit.items())
        lines.append(f"<tu>{tuvs}</tu>")
    lines += ["</body>", "</tmx>", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
