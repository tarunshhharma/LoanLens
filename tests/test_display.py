"""Tests for ui/display.py: pure formatting helpers for the Streamlit UI.

Run from the project root:
    pytest tests/test_display.py -v
"""

import pytest

from app.schema import LoanTerms
from ui.display import FIELD_LABELS, format_inr, format_value, term_rows

CITE = {"label": "Schedule A, page 19", "page_start": 19, "page_end": 19}


# --- format_inr: Indian digit grouping ------------------------------------------

@pytest.mark.parametrize("amount, expected", [
    (999, "Rs 999"),
    (1000, "Rs 1,000"),
    (120000, "Rs 1,20,000"),
    (500000, "Rs 5,00,000"),
    (12345678, "Rs 1,23,45,678"),
    (4991.9, "Rs 4,992"),        # rounded to whole rupees
])
def test_format_inr(amount, expected):
    assert format_inr(amount) == expected


# --- format_value ---------------------------------------------------------------

@pytest.mark.parametrize("field, value, expected", [
    ("loan_amount", 120000, "Rs 1,20,000"),
    ("emi", 5558, "Rs 5,558"),
    ("interest_rate", 19.25, "19.25% p.a."),
    ("rate_type", "floating", "Floating"),
    ("tenure_months", 240, "240 months (20 years)"),
    ("tenure_months", 30, "30 months (2.5 years)"),
    ("prepayment_charge_applies", True, "Yes"),
    ("bank_can_change_rate", False, "No"),
    ("penal_charges", "2% per month", "2% per month"),
])
def test_format_value(field, value, expected):
    assert format_value(field, value) == expected


# --- term_rows --------------------------------------------------------------------

def test_labels_cover_every_schema_field_in_order():
    assert list(FIELD_LABELS) == list(LoanTerms.model_fields)


def test_rows_show_value_and_source():
    terms = {name: None for name in LoanTerms.model_fields}
    terms["interest_rate"] = {"value": 19.25, "citation": CITE}
    rows = term_rows(terms)
    assert rows[1] == {"Term": "Interest rate", "Value": "19.25% p.a.",
                       "Source": "Schedule A, page 19"}


def test_missing_terms_say_not_stated():
    rows = term_rows({name: None for name in LoanTerms.model_fields})
    assert len(rows) == len(LoanTerms.model_fields)
    assert all(row["Value"] == "Not stated" and row["Source"] == "" for row in rows)
