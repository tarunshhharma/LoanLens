"""The LoanTerms schema: the key terms extracted from one loan agreement.

Every value travels with the citation it came from. A field is None when the
agreement doesn't state it (common in templates, where the amount is left blank).
"""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Reusable value types: the constraints live here, once.
Rupees = Annotated[float, Field(gt=0)]               # 500000, not "5,00,000"
Percent = Annotated[float, Field(gt=0, le=50)]       # 10.5 means 10.5% per annum
Months = Annotated[int, Field(gt=0, le=480)]         # at most 40 years
ShortText = Annotated[str, Field(min_length=1, max_length=500)]
RateType = Literal["fixed", "floating"]

T = TypeVar("T")

class Strict(BaseModel):
  # extra="forbid": an unknown field is an error, not silently dropped (catches schema drift).
  # str_strip_whitespace: "  2% per month  " -> "2% per month"
  model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Citation(Strict):
  label: str                        # "Clause 5.1, page 7"
  page_start: int = Field(gt=0)
  page_end: int = Field(gt=0)

class Term(Strict, Generic[T]):
  """One extracted value and where it came from."""
  value: T
  citation: Citation

class LoanTerms(Strict):
  loan_amount: Term[Rupees] | None = None
  interest_rate: Term[Percent] | None = None
  rate_type: Term[RateType] | None = None
  tenure_months: Term[Months] | None = None
  emi: Term[Rupees] | None = None
  processing_fee: Term[ShortText] | None = None
  prepayment_charge_applies: Term[bool] | None = None
  prepayment_charges: Term[ShortText] | None = None
  penal_charges: Term[ShortText] | None = None
  bank_can_change_rate: Term[bool] | None = None

  def found_fields(self) -> list[str]:
    """Names of the fields that have a value, in schema order."""
    return [name for name in type(self).model_fields if getattr(self, name) is not None]