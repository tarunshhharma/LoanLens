"""Risk flags: plain-Python rules over extracted LoanTerms.

Rules only read number and true/false fields; text fields (fees, penal charges) are
shown to the user, not computed on. Missing data never raises a flag. Every flag
carries the citations of the terms that triggered it, so the user can check the clause.
"""

from collections.abc import Callable
from typing import Literal

from app.schema import Citation, LoanTerms, Strict, Term

Severity = Literal["high", "medium", "low"]
SEVERITY_ORDER = {"high": 0, "medium":1, "low": 2}

HIGH_RATE_PERCENT = 18.0  # above this, flag the rate. A product choice, not a law.
EMI_TOLERANCE = 0.05      # the stated EMI may differ from the formula by 5% (rounding)

class RiskFlag(Strict):
  rule: str         
  severity: Severity
  title: str
  explanation: str
  citations: list[Citation]

def expected_emi(principal: float, annual_rate_percent: float, months: int) -> float:
  """Reducing-balance EMI: P * r * (1 + r)^n / ((1 + r)^n - 1), with r the monthly rate."""
  r = annual_rate_percent / 12/ 100
  growth = (1 + r) ** months
  return principal * r * growth / (growth -1)

def _value(term: Term | None):
  return None if term is None else term.value

def _cites(*terms: Term | None) -> list[Citation]:
  """Citations of the given terms, skipping missing ones and repeats."""
  citations = []
  for term in terms:
    if term is not None and term.citation not in citations:
      citations.append(term.citation)
  return citations


# --- Rules: each takes LoanTerms and returns a RiskFlag or None ----------------
def floating_rate_prepayment_charge(terms: LoanTerms) -> RiskFlag | None:
  if _value(terms.rate_type) != "floating" or _value(terms.prepayment_charge_applies) is not True:
    return None
  return RiskFlag(
    rule="floating_rate_prepayment_charge",
    severity="high",
    title="Prepayment charge on a floating-rate loan",
    explanation="The agreement charges for repaying early on a floating-rate loan. RBI has "
                "told banks not to levy foreclosure or prepayment charges on floating-rate "
                "term loans to individual borrowers. Check whether this applies to you.",
    citations=_cites(terms.rate_type, terms.prepayment_charge_applies),
  )


def prepayment_charge(terms: LoanTerms) -> RiskFlag | None:
  if _value(terms.prepayment_charge_applies) is not True or _value(terms.rate_type) == "floating":
    return None  # the floating case is the rule above, with a higher severity
  return RiskFlag(
    rule="prepayment_charge",
    severity="low",
    title="Charge for repaying early",
    explanation="Closing or part-paying the loan early costs extra. "
                "See the cited clause for the amount.",
    citations=_cites(terms.prepayment_charge_applies, terms.prepayment_charges),
  )


def bank_can_change_rate(terms: LoanTerms) -> RiskFlag | None:
  if _value(terms.bank_can_change_rate) is not True:
    return None
  if _value(terms.rate_type) == "fixed":
    return RiskFlag(
      rule="bank_can_change_rate",
      severity="high",
      title="A 'fixed' rate the bank can change",
      explanation="The rate is described as fixed, but the agreement lets the bank change it. "
                  "Your EMI or tenure could increase.",
      citations=_cites(terms.rate_type, terms.bank_can_change_rate),
    )
  return RiskFlag(
    rule="bank_can_change_rate",
    severity="medium",
    title="The bank can change your interest rate",
    explanation="The rate can be revised during the loan, so your EMI or tenure could increase.",
    citations=_cites(terms.bank_can_change_rate, terms.rate_type),
  )


def high_interest_rate(terms: LoanTerms) -> RiskFlag | None:
  rate = _value(terms.interest_rate)
  if rate is None or rate <= HIGH_RATE_PERCENT:
    return None
  return RiskFlag(
    rule="high_interest_rate",
    severity="medium",
    title="High interest rate",
    explanation=f"The rate is {rate}% per annum, above {HIGH_RATE_PERCENT}%.",
    citations=_cites(terms.interest_rate),
  )


def emi_mismatch(terms: LoanTerms) -> RiskFlag | None:
  amount, rate = _value(terms.loan_amount), _value(terms.interest_rate)
  months, emi = _value(terms.tenure_months), _value(terms.emi)
  if None in (amount, rate, months, emi):
    return None  # the check needs all four numbers
  expected = expected_emi(amount, rate, months)
  if abs(emi - expected) / expected <= EMI_TOLERANCE:
    return None
  return RiskFlag(
    rule="emi_mismatch",
    severity="medium",
    title="EMI doesn't match the amount, rate and tenure",
    explanation=f"The stated EMI is Rs {emi:,.0f}, but Rs {amount:,.0f} at {rate}% for "
                f"{months} months works out to about Rs {expected:,.0f}. Either a term was "
                "misread, or the EMI includes something else.",
    citations=_cites(terms.loan_amount, terms.interest_rate, terms.tenure_months, terms.emi),
  )


RULES: list[Callable[[LoanTerms], RiskFlag | None]] = [
  floating_rate_prepayment_charge,
  prepayment_charge,
  bank_can_change_rate,
  high_interest_rate,
  emi_mismatch,
]


def assess_risks(terms: LoanTerms) -> list[RiskFlag]:
  """Run every rule; return the flags, most severe first."""
  flags = [flag for rule in RULES if (flag := rule(terms)) is not None]
  return sorted(flags, key=lambda flag: SEVERITY_ORDER[flag.severity])