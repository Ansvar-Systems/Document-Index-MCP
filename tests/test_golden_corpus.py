"""Sentence-boundary F1 accuracy test against the golden corpus.

For each fixture, we parse the .txt file through TextParser, extract the
`char_start` of every produced sentence, and compare against the expected
starts listed in the sibling .expected.json. A boundary is a true positive
if the parser's char_start is within ±2 chars of an expected char_start.

The aggregate F1 across all 11 fixtures must be ≥ 0.98. This gate protects
against regressions in segmenter or parser offset tracking.

---

Labeling policy (applies to all expected.json files):

WHAT COUNTS AS A SENTENCE FOR CITATION PURPOSES
Each sentence start is the char offset of the first non-whitespace character
after the previous sentence's terminator (`.` `!` `?`), or at the paragraph
start (first non-whitespace after a blank line).

TERMINATORS
`.`, `!`, `?` end a sentence EXCEPT when the preceding word is an abbreviation
(see segmenter._ABBREVIATIONS). `§`, `:`, `;`, `,` never end a sentence.

ABBREVIATIONS THAT DO NOT TERMINATE
Art., §, e.g., i.e., etc. do NOT end a sentence — unless `etc.` is followed
immediately (after optional whitespace) by an uppercase letter, which signals
a new sentence rather than a continuation.

LIST ITEMS
Each item in a numbered (1. 2. 3.) or lettered ((a) (b) (c)) enumeration IS
a separate citeable sentence. The FIRST item is bundled with its colon-
introduced preamble into a single citation unit because the preamble alone
(ending in `:`) is not a complete sentence. Subsequent items, separated by
semicolons, each start their own citation unit.

  Example — fixture 04:
    [261] "The measures...following: (a) policies on risk analysis..."  ← intro+(a)
    [387] "(b) incident handling procedures"                            ← semicolon cut
    [421] "(c) business continuity measures..."                         ← semicolon cut

SECTION HEADINGS
Standalone section headings are NOT prose sentences and are not labeled.
Inline clause labels like "7.2 Competence: The organisation shall..." are part
of the prose sentence starting at the paragraph; the full sentence including
the label is labeled at the paragraph-start offset.

LABELING PROCESS
The expected_sentence_starts values in each .expected.json were derived by:
1. Reading the .txt file character by character without reference to parser output.
2. Applying the policy above to mark every sentence start.
3. Recording the first non-whitespace character offset for each sentence.

Each fixture was verified independently against the segmenter; any disagreements
were resolved in favour of the policy, and the segmenter was updated where it
diverged from the policy.
"""

import json
from pathlib import Path
import pytest

from document_index_mcp.parsers.text_parser import TextParser

FIXTURES = Path(__file__).parent / "fixtures" / "golden_corpus"
TOLERANCE_CHARS = 2
F1_THRESHOLD = 0.98


def _load_fixtures():
    fixtures = []
    for json_path in sorted(FIXTURES.glob("*.expected.json")):
        with open(json_path) as f:
            expected = json.load(f)
        txt_path = FIXTURES / expected["filename"]
        if not txt_path.exists():
            pytest.fail(f"Missing fixture file: {txt_path}")
        fixtures.append((txt_path, expected["expected_sentence_starts"]))
    return fixtures


def _parser_sentence_starts(txt_path: Path) -> list[int]:
    result = TextParser().parse(txt_path)
    starts: list[int] = []
    for section in result.sections:
        for para in section.paragraphs:
            for sent in para.sentences:
                starts.append(sent.char_start)
    return sorted(starts)


def _boundary_f1(predicted: list[int], expected: list[int]) -> tuple[float, float, float]:
    """Returns (precision, recall, f1) where a TP is a predicted boundary
    within ±TOLERANCE_CHARS of an expected boundary."""
    matched_expected: set[int] = set()
    tp = 0
    for p in predicted:
        for i, e in enumerate(expected):
            if i in matched_expected:
                continue
            if abs(p - e) <= TOLERANCE_CHARS:
                tp += 1
                matched_expected.add(i)
                break
    fp = len(predicted) - tp
    fn = len(expected) - len(matched_expected)
    if tp == 0:
        return (0.0, 0.0, 0.0)
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall)
    return (precision, recall, f1)


def test_golden_corpus_exists():
    fixtures = _load_fixtures()
    assert len(fixtures) == 11, f"Expected 11 fixtures, found {len(fixtures)}"


@pytest.mark.parametrize("txt_path,expected_starts", _load_fixtures())
def test_golden_corpus_per_document_f1(txt_path, expected_starts):
    predicted = _parser_sentence_starts(txt_path)
    p, r, f1 = _boundary_f1(predicted, expected_starts)
    # Per-document: log for debugging, but only aggregate is a hard gate
    print(f"{txt_path.name}: P={p:.3f} R={r:.3f} F1={f1:.3f}  "
          f"(predicted {len(predicted)}, expected {len(expected_starts)})")


def test_golden_corpus_aggregate_f1_meets_threshold():
    fixtures = _load_fixtures()
    total_tp = total_fp = total_fn = 0
    for txt_path, expected in fixtures:
        predicted = _parser_sentence_starts(txt_path)
        matched: set[int] = set()
        tp = 0
        for p in predicted:
            for i, e in enumerate(expected):
                if i in matched:
                    continue
                if abs(p - e) <= TOLERANCE_CHARS:
                    tp += 1
                    matched.add(i)
                    break
        total_tp += tp
        total_fp += len(predicted) - tp
        total_fn += len(expected) - len(matched)
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    print(f"Aggregate: P={precision:.3f} R={recall:.3f} F1={f1:.3f}")
    assert f1 >= F1_THRESHOLD, (
        f"Segmenter aggregate F1 {f1:.3f} below threshold {F1_THRESHOLD}. "
        f"TP={total_tp} FP={total_fp} FN={total_fn}"
    )
