from document_index_mcp.parsers.base import Paragraph, Sentence
from document_index_mcp.segmenter import segment_paragraphs, segment_section, segment_sentences


def test_segment_single_sentence():
    spans = segment_sentences("Hello world.")
    assert spans == [(0, 12, "Hello world.")]


def test_segment_two_sentences():
    spans = segment_sentences("Hello world. Goodbye world.")
    assert spans == [
        (0, 12, "Hello world."),
        (13, 27, "Goodbye world."),
    ]


def test_segment_question_and_exclamation():
    spans = segment_sentences("Really? Yes! Okay.")
    assert [s[2] for s in spans] == ["Really?", "Yes!", "Okay."]


def test_segment_empty_string():
    assert segment_sentences("") == []


def test_segment_preserves_offsets_exactly():
    text = "A short one. A slightly longer second sentence."
    spans = segment_sentences(text)
    for start, end, sent_text in spans:
        assert text[start:end] == sent_text


def test_segment_does_not_split_on_art():
    text = "See Art. 33 of the GDPR. It governs breach notification."
    spans = segment_sentences(text)
    assert len(spans) == 2
    assert "Art. 33" in spans[0][2]


def test_segment_does_not_split_on_eg_ie():
    text = "Controllers (e.g. the data exporter) must act. Processors act on instructions."
    spans = segment_sentences(text)
    assert len(spans) == 2


def test_segment_does_not_split_on_section_symbol():
    text = "See §4.2 for details. Section references are binding."
    spans = segment_sentences(text)
    assert len(spans) == 2


def test_segment_does_not_split_on_multi_dot_abbreviations():
    """e.g., i.e., etc. — dots inside the abbreviation are not boundaries."""
    text = "Security controls (e.g., MFA, logging, etc.) must be in place. This is not optional."
    spans = segment_sentences(text)
    assert len(spans) == 2


def test_segment_numbered_list_items_as_separate_sentences():
    text = "The Processor shall: 1. notify the Controller; 2. preserve evidence; 3. investigate."
    spans = segment_sentences(text)
    # The intro clause + 3 list items = 4 sentences, OR the intro + list as 1 sentence
    # depending on interpretation. For legal citation purposes we want each list
    # item citeable separately — so 4 sentences.
    assert len(spans) >= 3
    # Each of the three list items should appear as its own span
    items = [s[2] for s in spans]
    assert any("notify the Controller" in i for i in items)
    assert any("preserve evidence" in i for i in items)
    assert any("investigate" in i for i in items)


def test_segment_lettered_list_items():
    text = "Factors include: (a) intent; (b) scale; (c) harm. These guide enforcement."
    spans = segment_sentences(text)
    assert len(spans) >= 2


def test_paragraphs_split_on_blank_line():
    text = "First paragraph line 1.\nFirst paragraph line 2.\n\nSecond paragraph."
    paras = segment_paragraphs(text)
    assert len(paras) == 2
    assert paras[0][2].startswith("First paragraph")
    assert paras[1][2] == "Second paragraph."


def test_paragraphs_single_paragraph():
    text = "Only one paragraph here. It has two sentences."
    paras = segment_paragraphs(text)
    assert len(paras) == 1
    assert paras[0][0] == 0
    assert paras[0][1] == len(text)


def test_paragraphs_empty_text():
    assert segment_paragraphs("") == []


def test_paragraphs_offsets_exact():
    text = "P1 line 1.\n\nP2 first. P2 second."
    paras = segment_paragraphs(text)
    for start, end, ptext in paras:
        assert text[start:end] == ptext


def test_segment_section_yields_paragraphs_and_sentences():
    text = "Intro sentence one. Intro sentence two.\n\nSecond para first. Second para second."
    base = 100  # pretend this text starts at offset 100 in full_text
    paras = segment_section(text, base_offset=base)
    assert isinstance(paras, list)
    assert len(paras) == 2
    assert all(isinstance(p, Paragraph) for p in paras)
    # Offsets are absolute, shifted by base
    assert paras[0].char_start == 100
    # Sentences populated
    assert len(paras[0].sentences) == 2
    assert all(isinstance(s, Sentence) for s in paras[0].sentences)
    # Sentence offsets are also absolute and consistent with paragraph range
    for para in paras:
        for sent in para.sentences:
            assert para.char_start <= sent.char_start
            assert sent.char_end <= para.char_end
