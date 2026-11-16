"""Tests for app/risk.py: plain-Python risk rules over LoanTerms.

Run from the project root:
    pytest tests/test_risk.py -v
"""

import json

import pytest

from app.risk import EMI_TOLERANCE, HIGH_RATE_PERCENT, assess_risks, expected_emi
from app.schema import LoanTerms


def cite(label="Clause 5.1, page 7", page=7):
    return {"label": label, "page_start": page, "page_end": page}


def terms(**values):
    """terms(rate_type="floating") -> LoanTerms with a cited value per field.
    Pass (value, label) to give a field its own citation label."""
    data = {}
    for name, value in values.items():
        if isinstance(value, tuple):
            value, label = value
            data[name] = {"value": value, "citation": cite(label)}
        else:
            data[name] = {"value": value, "citation": cite(f"Clause for {name}, page 7")}
    return LoanTerms.model_validate(data)


def rules(flags):
    return [flag.rule for flag in flags]


# --- expected_emi -------------------------------------------------------------

def test_expected_emi_matches_the_standard_formula():
    # Rs 5,00,000 at 10.5% for 20 years: about Rs 4,992 a month
    assert expected_emi(500000, 10.5, 240) == pytest.approx(4991.9, abs=1)


def test_expected_emi_short_loan():
    # Rs 1,20,000 at 19.25% for 24 months: about Rs 6,064
    assert expected_emi(120000, 19.25, 24) == pytest.approx(6064, abs=1)


# --- No data, no flags ----------------------------------------------------------

def test_no_terms_means_no_flags():
    assert assess_risks(LoanTerms()) == []


# --- Prepayment charges ----------------------------------------------------------

def test_prepayment_charge_on_floating_rate_is_high():
    flags = assess_risks(terms(rate_type="floating", prepayment_charge_applies=True))
    assert rules(flags) == ["floating_rate_prepayment_charge"]
    assert flags[0].severity == "high"


def test_flag_cites_every_term_that_triggered_it():
    flags = assess_risks(terms(rate_type=("floating", "Schedule A, page 19"),
                               prepayment_charge_applies=(True, "Schedule 2, page 22")))
    assert [c.label for c in flags[0].citations] == ["Schedule A, page 19", "Schedule 2, page 22"]


def test_same_clause_is_cited_once():
    flags = assess_risks(terms(rate_type=("floating", "Schedule A, page 19"),
                               prepayment_charge_applies=(True, "Schedule A, page 19")))
    assert [c.label for c in flags[0].citations] == ["Schedule A, page 19"]


def test_prepayment_charge_on_fixed_rate_is_low():
    flags = assess_risks(terms(rate_type="fixed", prepayment_charge_applies=True))
    assert rules(flags) == ["prepayment_charge"]
    assert flags[0].severity == "low"


def test_prepayment_charge_with_unknown_rate_type_is_low():
    flags = assess_risks(terms(prepayment_charge_applies=True))
    assert rules(flags) == ["prepayment_charge"]


def test_no_prepayment_charge_no_flag():
    assert assess_risks(terms(rate_type="floating", prepayment_charge_applies=False)) == []


def test_unknown_prepayment_never_raises_a_flag():
    # Missing data is not evidence of a risk
    assert assess_risks(terms(rate_type="floating")) == []


# --- Bank can change the rate -----------------------------------------------------

def test_bank_can_change_a_fixed_rate_is_high():
    flags = assess_risks(terms(rate_type="fixed", bank_can_change_rate=True))
    assert rules(flags) == ["bank_can_change_rate"]
    assert flags[0].severity == "high"


@pytest.mark.parametrize("rate_type", ["floating", None])
def test_bank_can_change_a_floating_or_unknown_rate_is_medium(rate_type):
    values = {"bank_can_change_rate": True}
    if rate_type:
        values["rate_type"] = rate_type
    flags = assess_risks(terms(**values))
    assert rules(flags) == ["bank_can_change_rate"]
    assert flags[0].severity == "medium"


def test_bank_cannot_change_rate_no_flag():
    assert assess_risks(terms(bank_can_change_rate=False)) == []


# --- High interest rate ------------------------------------------------------------

def test_rate_above_threshold_is_flagged():
    flags = assess_risks(terms(interest_rate=19.25))
    assert rules(flags) == ["high_interest_rate"]
    assert flags[0].severity == "medium"
    assert "19.25" in flags[0].explanation


def test_rate_at_threshold_is_not_flagged():
    assert assess_risks(terms(interest_rate=HIGH_RATE_PERCENT)) == []


# --- EMI consistency -----------------------------------------------------------------

def test_consistent_emi_no_flag():
    assert assess_risks(terms(loan_amount=500000, interest_rate=10.5,
                              tenure_months=240, emi=4992)) == []


def test_emi_within_tolerance_no_flag():
    emi = 4992 * (1 + EMI_TOLERANCE * 0.9)
    assert assess_risks(terms(loan_amount=500000, interest_rate=10.5,
                              tenure_months=240, emi=emi)) == []


def test_emi_that_does_not_match_the_formula_is_flagged():
    flags = assess_risks(terms(loan_amount=500000, interest_rate=10.5,
                               tenure_months=240, emi=6000))
    assert rules(flags) == ["emi_mismatch"]
    assert flags[0].severity == "medium"
    assert len(flags[0].citations) == 4


def test_emi_check_needs_all_four_values():
    assert assess_risks(terms(loan_amount=500000, interest_rate=10.5, emi=6000)) == []


# --- Ordering and output -----------------------------------------------------------------

def test_flags_are_sorted_high_medium_low():
    flags = assess_risks(terms(rate_type="fixed", prepayment_charge_applies=True,
                               bank_can_change_rate=True, interest_rate=19.25))
    assert [f.severity for f in flags] == ["high", "medium", "low"]


def test_flags_dump_to_plain_json():
    flags = assess_risks(terms(rate_type="floating", prepayment_charge_applies=True))
    json.dumps([flag.model_dump() for flag in flags])
