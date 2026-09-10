# this_file: tests/test_tmx.py
"""TMX writer."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vexy_paraltext.tmx import write_tmx


def test_write_tmx_when_units_then_valid_compact_xml(tmp_path: Path):
    out = tmp_path / "x.tmx"
    write_tmx([{"en": "A & B <c>", "de": "A und B"}, {"en": "x", "fr": "y"}], out, srclang="en")
    root = ET.parse(out).getroot()
    assert root.attrib["version"] == "1.4"
    tus = root.findall("./body/tu")
    assert len(tus) == 2
    segs = tus[0].findall("tuv")
    assert segs[0].attrib["{http://www.w3.org/XML/1998/namespace}lang"] == "en"
    assert segs[0].find("seg").text == "A & B <c>"
    assert out.read_text().count("\n") == 8, "one line per TU, no pretty-printing"


def test_write_tmx_when_no_units_then_empty_body(tmp_path: Path):
    out = tmp_path / "e.tmx"
    write_tmx([], out, srclang="en")
    assert ET.parse(out).getroot().findall("./body/tu") == []


@pytest.mark.parametrize("codepoint", [*range(9), 11, 12, *range(14, 32), 0xD800, 0xDFFF, 0xFFFE, 0xFFFF])
def test_write_tmx_when_forbidden_character_then_removed(tmp_path: Path, codepoint: int):
    out = tmp_path / "clean.tmx"
    bad = chr(codepoint)
    write_tmx([{f"e{bad}n": f"before{bad}after", "de": bad}], out, srclang=f"e{bad}n", tool=f"my{bad}tool")
    root = ET.parse(out).getroot()
    assert root.find("header").attrib["creationtool"] == "mytool", "clean metadata too"
    assert root.find("header").attrib["srclang"] == "en"
    assert root.find("./body/tu/tuv").attrib["{http://www.w3.org/XML/1998/namespace}lang"] == "en"
    assert [seg.text for seg in root.findall("./body/tu/tuv/seg")] == ["beforeafter", None], "retain units even if empty"


def test_write_tmx_when_legal_unicode_then_preserved(tmp_path: Path):
    out = tmp_path / "unicode.tmx"
    text = "\t\n\r & < > Ł 中文 😀 \u0020\ud7ff\ue000\ufffd\U00010000\U0010ffff"
    write_tmx([{"en": text}], out, srclang="en")
    assert ET.parse(out).find("./body/tu/tuv/seg").text == text.replace("\r", "\n"), "XML normalizes literal CR"


def test_write_tmx_when_attributes_contain_markup_then_escaped(tmp_path: Path):
    out = tmp_path / "attributes.tmx"
    value = "a & <b> \"double\" 'single'\t\n\r"
    write_tmx([{value: "literal &#4;"}], out, srclang=value, tool=value)
    root = ET.parse(out).getroot()
    assert root.find("header").attrib["creationtool"] == value
    assert root.find("header").attrib["srclang"] == value
    assert root.find("./body/tu/tuv").attrib["{http://www.w3.org/XML/1998/namespace}lang"] == value
    assert root.find("./body/tu/tuv/seg").text == "literal &#4;", "do not interpret text as character references"
