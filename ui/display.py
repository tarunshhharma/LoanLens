"""Formatting helpers for the Streamlit UI. Plain functions, so they can be unit-tested."""

# Human labels for LoanTerms fields, in schema order.
FIELD_LABELS = {
  "loan_amount": "Loan amount",
  "interest_rate": "Interest rate",
  "rate_type": "Rate type",
  "tenure_months": "Tenure",
  "emi": "EMI",
  "processing_fee": "Processing fee",
  "prepayment_charge_applies": "Prepayment charge applies",
  "prepayment_charges": "Prepayment charges",
  "penal_charges": "Penal charges",
  "bank_can_change_rate": "Bank can change the rate",
}

MONEY_FIELDS = {"loan_amount", "emi"}


def format_inr(amount: float) -> str:
  """Indian digit grouping: 1234567 -> 'Rs 12,34,567' (last 3 digits, then pairs)."""
  digits = str(round(amount))
  if len(digits) <= 3:
    return f"Rs {digits}"
  head, tail = digits[:-3], digits[-3:]
  groups = []
  while len(head) > 2:
    groups.insert(0, head[-2:])
    head = head[:-2]
  groups.insert(0, head)
  return "Rs " + ",".join(groups) + "," + tail


def format_value(field: str, value) -> str:
  if field in MONEY_FIELDS:
    return format_inr(value)
  if field == "interest_rate":
    return f"{value:g}% p.a."
  if field == "rate_type":
    return value.capitalize()
  if field == "tenure_months":
    return f"{value} months ({round(value / 12, 1):g} years)"
  if isinstance(value, bool):
    return "Yes" if value else "No"
  return str(value)


def term_rows(terms: dict) -> list[dict]:
  """The /extract "terms" dict -> one table row per field, in schema order."""
  rows = []
  for field, label in FIELD_LABELS.items():
    term = terms.get(field)
    if term is None:
      rows.append({"Term": label, "Value": "Not stated", "Source": ""})
    else:
      rows.append({"Term": label, "Value": format_value(field, term["value"]),
                   "Source": term["citation"]["label"]})
  return rows
