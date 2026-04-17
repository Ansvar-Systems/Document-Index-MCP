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
