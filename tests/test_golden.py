"""Checks that evals/golden.jsonl is well-formed, so the eval script (Step 5) can trust it.

Run from the project root:
    pytest tests/test_golden.py -v
"""

import json
from collections import Counter
from pathlib import Path

import pytest

GOLDEN = Path("evals/golden.jsonl")
DOCS = {"au_personal", "au_home", "rbl_home"}
TYPES = {"clause", "schedule", "definition", "plain", "not_found"}
KEYS = {"id", "doc", "type", "question", "found", "pages", "clause", "answer_includes", "source"}

ITEMS = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_forty_questions_with_unique_ids():
    assert len(ITEMS) == 40
    assert len({item["id"] for item in ITEMS}) == 40


def test_every_agreement_and_every_type_is_covered():
    assert set(Counter(item["doc"] for item in ITEMS)) == DOCS
    assert set(Counter(item["type"] for item in ITEMS)) == TYPES


def test_a_fair_share_are_not_found_questions():
    # Saying "not found" is half of the job: at least 6 of 40, on every agreement
    not_found = [item for item in ITEMS if not item["found"]]
    assert len(not_found) >= 6
    assert {item["doc"] for item in not_found} == DOCS


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item["id"])
def test_item_is_well_formed(item):
    assert set(item) == KEYS
    assert item["doc"] in DOCS
    assert item["type"] in TYPES
    assert item["question"].endswith("?")
    assert item["source"]
    for expected in item["answer_includes"]:
        # a string, or a list of alternatives (any one is enough)
        assert isinstance(expected, str) or (isinstance(expected, list) and expected)

    if item["found"]:
        # a list of acceptable page ranges: some facts appear in two places (e.g. clause + KFS)
        assert item["pages"]
        for start, end in item["pages"]:
            assert 1 <= start <= end
        assert item["type"] != "not_found"
    else:
        assert item["type"] == "not_found"
        assert item["pages"] is None and item["clause"] is None
        assert item["answer_includes"] == []
