"""Tests for app/schema.py: the LoanTerms extraction schema.

Run from the project root:
    pytest tests/test_schema.py -v
"""

import pytest
from pydantic import ValidationError

from app.schema import Citation, LoanTerms

CITE = {"label": "Clause 5.1, page 7", "page_start": 7, "page_end": 7}


def term(value):
    return {"value": value, "citation": CITE}


# --- Valid documents ----------------------------------------------------------

def test_every_field_can_be_missing():
    # A template agreement often leaves the amount and rate blank: None = "not in the agreement"
    terms = LoanTerms()
    assert terms.loan_amount is None
    assert terms.rate_type is None


def test_full_document_parses():
    terms = LoanTerms.model_validate({
        "loan_amount": term(500000),
        "interest_rate": term(10.5),
        "rate_type": term("floating"),
        "tenure_months": term(240),
        "emi": term(4992.0),
        "processing_fee": term("1% of the loan amount plus GST"),
        "prepayment_charge_applies": term(False),
        "prepayment_charges": term("Nil for floating rate loans"),
        "penal_charges": term("Rs 0.65 per Rs 1,000 per day on the overdue EMI"),
        "bank_can_change_rate": term(True),
    })
    assert terms.loan_amount.value == 500000
    assert terms.interest_rate.value == 10.5
    assert terms.rate_type.value == "floating"
    assert terms.tenure_months.citation == Citation(**CITE)


def test_citation_is_kept_with_its_value():
    terms = LoanTerms.model_validate({"interest_rate": term(9.25)})
    assert terms.interest_rate.citation.label == "Clause 5.1, page 7"
    assert terms.interest_rate.citation.page_start == 7


def test_text_is_stripped():
    terms = LoanTerms.model_validate({"penal_charges": term("  2% per month  ")})
    assert terms.penal_charges.value == "2% per month"


def test_dumps_to_plain_json():
    # The API returns model_dump(); missing fields stay as null
    dumped = LoanTerms.model_validate({"tenure_months": term(60)}).model_dump()
    assert dumped["tenure_months"] == {"value": 60, "citation": CITE}
    assert dumped["loan_amount"] is None


# --- Values the schema must reject ---------------------------------------------

@pytest.mark.parametrize("field, bad_value", [
    ("loan_amount", 0),            # amounts must be positive
    ("loan_amount", -500000),
    ("emi", 0),
    ("interest_rate", 0),          # a 0% home loan is an extraction error
    ("interest_rate", 60),         # percent per annum, at most 50
    ("tenure_months", 0),
    ("tenure_months", 600),        # at most 40 years = 480 months
    ("tenure_months", 12.5),       # whole months only
    ("rate_type", "variable"),     # only "fixed" or "floating"
    ("processing_fee", ""),        # empty text is not a value; use null instead
    ("penal_charges", "x" * 501),  # text values are short summaries
])
def test_rejects_impossible_values(field, bad_value):
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({field: term(bad_value)})


def test_rejects_amount_written_as_indian_formatted_text():
    # The model must return a number; "5,00,000" is not one
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({"loan_amount": term("5,00,000")})


def test_a_value_without_a_citation_is_rejected():
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({"loan_amount": {"value": 500000}})


def test_citation_pages_must_be_positive():
    bad = {"value": 500000, "citation": {**CITE, "page_start": 0}}
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({"loan_amount": bad})


# --- Schema drift: unknown fields are errors, not silently dropped ---------------

def test_unknown_top_level_field_is_rejected():
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({"loan_amout": term(500000)})  # typo by the model


def test_unknown_field_inside_a_term_is_rejected():
    with pytest.raises(ValidationError):
        LoanTerms.model_validate({"emi": {"value": 4992, "citation": CITE, "confidence": 0.9}})


# --- Helper -------------------------------------------------------------------

def test_found_fields_lists_only_the_fields_with_values():
    terms = LoanTerms.model_validate({"interest_rate": term(9.25), "tenure_months": term(60)})
    assert terms.found_fields() == ["interest_rate", "tenure_months"]
