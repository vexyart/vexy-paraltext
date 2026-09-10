# this_file: tests/test_segment.py
"""Sentence segmentation on converter-style markdown."""

from vexy_paraltext.segment import clean_markdown, drop_repeats, split_sentences

MD = """![p1](/tmp/x.jpg)

/01/

Cover of the journal *Caractère*, no.12, 1954.

The character shapes appear well balanced. They are quiet and dis-
tinct in spite of their unusual distribution.Nothing else matters here &amp; now.

# Heading

<b>Bold</b> play­ed around. Short."""


def test_clean_markdown_when_images_and_markup_then_reflowed_paragraphs():
    paras = clean_markdown(MD)
    assert paras[0].startswith("Cover of the journal Caractère")
    assert "distinct in spite" in paras[1], "line-break hyphen must be joined"
    assert "distribution. Nothing" in paras[1], "glued sentences get a space"
    assert "& now" in paras[1], "HTML entities decoded"
    assert "played around" in paras[-1], "soft hyphen removed, tags stripped"
    assert all("![" not in p and "/01/" not in p for p in paras)


def test_split_sentences_when_english_then_pysbd_and_junk_filtered():
    sents = split_sentences(MD, "en")
    assert "The character shapes appear well balanced." in sents
    assert "Short." not in sents, "too short to keep"
    assert "Heading" not in sents


def test_split_sentences_when_unsupported_language_then_regex_fallback():
    sents = split_sentences("Primeira frase completa aqui. Segunda frase completa aqui!", "pt")
    assert sents == ["Primeira frase completa aqui.", "Segunda frase completa aqui!"]


def test_split_sentences_when_empty_then_empty():
    assert split_sentences("", "de") == []
    assert split_sentences("   \n\n  ", "de") == []


def test_drop_repeats_when_running_head_then_removed():

    sents = ["Running head here"] * 3 + ["Body sentence one.", "Body sentence one."]
    assert drop_repeats(sents) == ["Body sentence one.", "Body sentence one."]


def test_split_sentences_when_mostly_digits_then_dropped():
    assert split_sentences("380 Frutiger 1957 1962 1975 Capitalis 22", "en") == []
