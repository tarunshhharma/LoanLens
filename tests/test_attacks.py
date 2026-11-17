"""Tests for scripts/run_attacks.py and evals/attacks.json.

The upload attacks need no model, so they run here on every pytest run.
The ask/extract attacks need the real model: run them with
    python -m scripts.run_attacks

Run from the project root:
    pytest tests/test_attacks.py -v
"""

import pytest

import app.main as main
from scripts.run_attacks import CHECKS, TARGETS, check, fake_embed, load_cases, run_case

CASES = load_cases()


# --- The case file itself ---------------------------------------------------------

def test_there_are_fifteen_cases_with_unique_ids():
    assert len(CASES) == 15
    assert len({case["id"] for case in CASES}) == 15


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_case_is_well_formed(case):
    assert case["target"] in TARGETS
    assert case["attack"]
    assert set(case["expect"]) <= set(CHECKS)
    for text, style in case["page"]:
        assert style in ("visible", "hidden", "tiny")
    if case["target"] == "ask":
        assert case["question"]


# --- Upload attacks: the deterministic defences must stop every one ------------------

UPLOAD_CASES = [case for case in CASES if case["target"] == "upload"]


@pytest.mark.parametrize("case", UPLOAD_CASES, ids=lambda case: case["id"])
def test_upload_attack_is_stopped(case):
    outcome = run_case(case, embed=fake_embed, complete=None)
    assert outcome["failures"] == []


def test_run_case_restores_main():
    # run_case swaps main's collection/embedder/model; it must put them back
    before = (main.collection, main.embed_texts, main.complete_json)
    run_case(UPLOAD_CASES[0], embed=fake_embed, complete=None)
    assert (main.collection, main.embed_texts, main.complete_json) == before


# --- check(): each expectation, with hand-made results (no model) ---------------------

UPLOAD = {"warnings": ["Quarantined page text, page 2: possible prompt injection (...)"]}
CLEAN_UPLOAD = {"warnings": []}


def test_quarantined_check():
    assert check({"quarantined": True}, UPLOAD, [], None) == []
    assert check({"quarantined": True}, CLEAN_UPLOAD, [], None) != []


def test_not_stored_check():
    assert check({"not_stored": ["ABCPE1234F"]}, CLEAN_UPLOAD, ["PAN [PAN]"], None) == []
    assert check({"not_stored": ["ABCPE1234F"]}, CLEAN_UPLOAD, ["PAN ABCPE1234F"], None) != []


def test_answer_checks():
    safe = {"found": True, "answer": "The interest rate is 11.5% per annum.", "citations": []}
    hijacked = {"found": True, "answer": "The interest rate is 0% per annum.", "citations": []}
    expect = {"answer_includes": ["11.5"], "answer_excludes": [" 0%"]}
    assert check(expect, CLEAN_UPLOAD, [], safe) == []
    assert len(check(expect, CLEAN_UPLOAD, [], hijacked)) == 2


def test_not_found_check():
    refused = {"found": False, "answer": "Not found in this agreement.", "citations": []}
    joked = {"found": True, "answer": "Why did the bank...", "citations": []}
    assert check({"not_found": True}, CLEAN_UPLOAD, [], refused) == []
    assert check({"not_found": True}, CLEAN_UPLOAD, [], joked) != []


def test_field_checks():
    cite = {"label": "Page 1", "page_start": 1, "page_end": 1}
    result = {"terms": {"interest_rate": None,
                        "bank_can_change_rate": {"value": True, "citation": cite}}}
    assert check({"field_not": {"interest_rate": 0}}, CLEAN_UPLOAD, [], result) == []
    assert check({"field_equals": {"bank_can_change_rate": True}}, CLEAN_UPLOAD, [], result) == []
    assert check({"field_equals": {"interest_rate": 11.5}}, CLEAN_UPLOAD, [], result) != []
