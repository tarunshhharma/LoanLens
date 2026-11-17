"""Tests for the scoring logic in scripts/run_evals.py (no model, no PDFs).

The full eval needs the sample agreements and an API key:
    python -m scripts.run_evals

Run from the project root:
    pytest tests/test_evals.py -v
"""

import pytest
from scripts.run_evals import includes_all, load_golden, overlaps, score_item, summarize

# --- overlaps -----------------------------------------------------------------------

@pytest.mark.parametrize("span, expected, result", [
    ({"page_start": 4, "page_end": 4}, [4, 4], True),
    ({"page_start": 3, "page_end": 5}, [4, 4], True),    # chunk spans the expected page
    ({"page_start": 13, "page_end": 13}, [13, 14], True),
    ({"page_start": 14, "page_end": 16}, [13, 14], True),  # partial overlap counts
    ({"page_start": 5, "page_end": 6}, [4, 4], False),
    ({"page_start": 1, "page_end": 3}, [4, 4], False),
])
def test_overlaps(span, expected, result):
    assert overlaps(span, expected) is result


# --- includes_all -------------------------------------------------------------------

def test_includes_all_is_case_insensitive():
    assert includes_all("Courts at JAIPUR have jurisdiction.", ["jaipur"])


def test_every_expected_item_must_appear():
    assert includes_all("Up to 4% with a minimum of Rs 2000", ["4%", "2000"])
    assert not includes_all("Up to 4% of the loan amount", ["4%", "2000"])


def test_a_list_means_any_one_alternative():
    assert includes_all("Up to six times a year", [["six", "6"]])
    assert includes_all("Up to 6 times a year", [["six", "6"]])
    assert not includes_all("Twice a year", [["six", "6"]])


def test_nothing_expected_is_always_satisfied():
    assert includes_all("anything", [])


# --- score_item ---------------------------------------------------------------------

FOUND_ITEM = {"id": "P04", "type": "schedule", "found": True, "pages": [[13, 14]],
              "answer_includes": ["0.65"]}
# A fact stated in two places: Schedule 2 (pages 13-14) and the KFS (page 18)
TWO_PLACES_ITEM = {"id": "P08", "type": "plain", "found": True, "pages": [[13, 14], [18, 18]],
                   "answer_includes": [["3", "three"]]}
NOT_FOUND_ITEM = {"id": "P15", "type": "not_found", "found": False, "pages": None,
                  "answer_includes": []}


def chunk(page_start, page_end):
    return {"id": "x", "text": "...", "metadata": {"page_start": page_start, "page_end": page_end}}


def answer(found, text, cited_pages=()):
    return {"found": found, "answer": text,
            "citations": [{"page_start": s, "page_end": e} for s, e in cited_pages]}


def test_perfect_found_item():
    score = score_item(FOUND_ITEM, [chunk(4, 4), chunk(13, 14)],
                       answer(True, "Rs 0.65 per Rs 1000 daily.", [(13, 14)]))
    assert score == {"id": "P04", "type": "schedule", "found": True,
                     "retrieval_hit": True, "citation_hit": True, "correct": True}


def test_retrieval_miss_is_recorded_separately_from_the_answer():
    score = score_item(FOUND_ITEM, [chunk(4, 4)], answer(True, "Not sure: 0.65?", [(4, 4)]))
    assert score["retrieval_hit"] is False
    assert score["citation_hit"] is False
    assert score["correct"] is True  # the words are there, but the evidence is wrong


def test_any_acceptable_location_counts():
    score = score_item(TWO_PLACES_ITEM, [chunk(17, 19)],
                       answer(True, "You have 3 days to cancel.", [(17, 19)]))
    assert score["retrieval_hit"] is True and score["citation_hit"] is True


def test_found_item_answered_not_found_is_wrong():
    score = score_item(FOUND_ITEM, [chunk(13, 14)], answer(False, "Not found in this agreement."))
    assert score["retrieval_hit"] is True
    assert score["correct"] is False


def test_not_found_item_scores_only_correctness():
    refused = score_item(NOT_FOUND_ITEM, [chunk(1, 1)], answer(False, "Not found in this agreement."))
    answered = score_item(NOT_FOUND_ITEM, [chunk(1, 1)], answer(True, "The CEO is ...", [(1, 1)]))
    assert refused["correct"] is True and answered["correct"] is False
    assert refused["retrieval_hit"] is None and refused["citation_hit"] is None


# --- summarize ----------------------------------------------------------------------

def test_summary_counts_each_metric_over_the_right_questions():
    scores = [
        {"id": "a", "type": "clause", "found": True, "retrieval_hit": True, "citation_hit": True, "correct": True},
        {"id": "b", "type": "clause", "found": True, "retrieval_hit": True, "citation_hit": False, "correct": False},
        {"id": "c", "type": "schedule", "found": True, "retrieval_hit": False, "citation_hit": False, "correct": False},
        {"id": "d", "type": "schedule", "found": True, "retrieval_hit": True, "citation_hit": True, "correct": True},
        {"id": "e", "type": "not_found", "found": False, "retrieval_hit": None, "citation_hit": None, "correct": True},
    ]
    summary = summarize(scores)
    assert summary["retrieval_hit_rate"] == 0.75   # 3 of 4 found questions
    assert summary["citation_accuracy"] == 0.5     # 2 of 4
    assert summary["answer_accuracy"] == 0.5       # 2 of 4
    assert summary["not_found_accuracy"] == 1.0    # 1 of 1
    assert summary["overall_accuracy"] == 0.6      # 3 of 5
    assert summary["by_type"] == {"clause": 0.5, "schedule": 0.5, "not_found": 1.0}


# --- The real golden set loads -------------------------------------------------------

def test_load_golden():
    items = load_golden()
    assert len(items) == 40
    assert items[0]["id"] == "P01"
