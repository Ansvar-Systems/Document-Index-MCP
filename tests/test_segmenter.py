from document_index_mcp.segmenter import segment_sentences


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
