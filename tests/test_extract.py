"""Tests for app/extract.py, with a FAKE search and a FAKE model (no OpenAI, no Chroma).

Run from the project root:
    pytest tests/test_extract.py -v
"""

import json

from app.extract import (
    FIELD_GROUPS,
    build_extraction_prompt,
    extract_terms,
    parse_extraction,
    validate_terms,
)
from app.schema import LoanTerms


def chunk(kind, text, page, **metadata):
    return {"id": "x", "text": text,
            "metadata": {"kind": kind, "page_start": page, "page_end": page, **metadata}}


RATE = chunk("clause", "5.1 Interest at 10.5% per annum, floating", 7, number="5.1")
AMOUNT = chunk("clause", "2.1 The Bank agrees to lend Rs 5,00,000", 4, number="2.1")
CHUNKS = [RATE, AMOUNT]


# --- FIELD_GROUPS -------------------------------------------------------------

def test_every_schema_field_is_extracted_exactly_once():
    asked = [name for group in FIELD_GROUPS for name in group.fields]
    assert sorted(asked) == sorted(LoanTerms.model_fields)


# --- build_extraction_prompt --------------------------------------------------

def test_prompt_lists_numbered_sources_and_the_fields():
    prompt = build_extraction_prompt({"interest_rate": "rate, percent per annum"}, CHUNKS)
    assert "[1] Clause 5.1, page 7\n5.1 Interest at 10.5%" in prompt
    assert "[2] Clause 2.1, page 4" in prompt
    assert "- interest_rate: rate, percent per annum" in prompt


# --- parse_extraction ---------------------------------------------------------

FIELDS = {"interest_rate": "...", "loan_amount": "...", "emi": "..."}


def parse(reply: dict):
    return parse_extraction(json.dumps(reply), FIELDS, CHUNKS)


def test_value_gets_the_citation_of_its_source():
    candidates, warnings = parse({"interest_rate": {"value": 10.5, "source": 1}})
    assert candidates == {"interest_rate": {
        "value": 10.5,
        "citation": {"label": "Clause 5.1, page 7", "page_start": 7, "page_end": 7},
    }}
    assert warnings == []


def test_null_means_not_in_the_agreement_and_is_not_a_warning():
    candidates, warnings = parse({"interest_rate": None, "loan_amount": None})
    assert candidates == {}
    assert warnings == []


def test_null_value_with_a_source_is_also_not_found():
    # Real reply on AU home's blank template: {"value": null, "source": 3}
    candidates, warnings = parse({"loan_amount": {"value": None, "source": 1}})
    assert candidates == {}
    assert warnings == []


def test_missing_field_is_treated_as_null():
    candidates, warnings = parse({})
    assert candidates == {}
    assert warnings == []


def test_invented_source_drops_the_value_with_a_warning():
    candidates, warnings = parse({"loan_amount": {"value": 500000, "source": 9}})
    assert candidates == {}
    assert len(warnings) == 1 and "loan_amount" in warnings[0]


def test_boolean_or_text_source_is_not_a_source():
    candidates, _ = parse({"loan_amount": {"value": 500000, "source": True},
                           "emi": {"value": 4992, "source": "2"}})
    assert candidates == {}


def test_value_without_the_value_key_is_dropped():
    candidates, warnings = parse({"emi": {"source": 1}})
    assert candidates == {}
    assert "emi" in warnings[0]


def test_unrequested_field_is_ignored_with_a_warning():
    # schema drift: the model adds a key nobody asked for
    candidates, warnings = parse({"interest_rate": {"value": 10.5, "source": 1},
                                  "confidence": 0.9})
    assert list(candidates) == ["interest_rate"]
    assert any("confidence" in w for w in warnings)


def test_broken_json_gives_nothing_and_a_warning():
    candidates, warnings = parse_extraction("Sorry, I can't", FIELDS, CHUNKS)
    assert candidates == {}
    assert len(warnings) == 1


# --- validate_terms -----------------------------------------------------------

CITE = {"label": "Clause 5.1, page 7", "page_start": 7, "page_end": 7}


def test_valid_candidates_become_loan_terms():
    terms, warnings = validate_terms({"interest_rate": {"value": 10.5, "citation": CITE}})
    assert terms.interest_rate.value == 10.5
    assert warnings == []


def test_one_invalid_field_is_dropped_and_the_rest_are_kept():
    terms, warnings = validate_terms({
        "interest_rate": {"value": 60, "citation": CITE},        # over 50%: invalid
        "tenure_months": {"value": 240, "citation": CITE},
    })
    assert terms.interest_rate is None
    assert terms.tenure_months.value == 240
    assert len(warnings) == 1 and "interest_rate" in warnings[0]


# --- extract_terms ------------------------------------------------------------

def fake_model(answers: dict):
    """Answers only the fields that appear in the prompt, like a real model would."""
    calls = []

    def complete(system, user):
        calls.append(user)
        return json.dumps({name: value for name, value in answers.items() if f"- {name}:" in user})

    complete.calls = calls
    return complete


def test_extracts_across_all_groups():
    model = fake_model({
        "interest_rate": {"value": 10.5, "source": 1},
        "rate_type": {"value": "floating", "source": 1},
        "penal_charges": {"value": "2% per month", "source": 2},
    })
    result = extract_terms(lambda query: CHUNKS, model)
    terms = result["terms"]
    assert terms.interest_rate.value == 10.5
    assert terms.rate_type.citation.label == "Clause 5.1, page 7"
    assert terms.penal_charges.value == "2% per month"
    assert terms.loan_amount is None
    assert result["warnings"] == []


def test_one_model_call_per_group():
    model = fake_model({})
    extract_terms(lambda query: CHUNKS, model)
    assert len(model.calls) == len(FIELD_GROUPS)


def test_each_call_asks_only_its_own_fields():
    model = fake_model({})
    extract_terms(lambda query: CHUNKS, model)
    for group, prompt in zip(FIELD_GROUPS, model.calls):
        for other in FIELD_GROUPS:
            if other is not group:
                assert not any(f"- {name}:" in prompt for name in other.fields)


def test_group_with_no_chunks_makes_no_model_call():
    model = fake_model({})
    result = extract_terms(lambda query: [], model)
    assert model.calls == []
    assert result["terms"].found_fields() == []
