"""Mask personal data before anything is stored in Chroma or sent to OpenAI.

Redaction happens once, right after text extraction in /upload, so every later step
(cleaning, chunks, embeddings, prompts, the API response) only ever sees the masked text.
Each match is replaced by its kind in brackets, e.g. "[PAN]", so a reader (or the model)
still knows something was there.
"""

import re
from collections import Counter

# Order matters: emails first (they can contain digits), Aadhaar before phone and account
# (a 12-digit Aadhaar must not be half-matched as something shorter).
PATTERNS = [
  ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
  # PAN: 5 letters, 4 digits, 1 letter. The 4th letter is the holder type (P = person, ...).
  ("PAN", re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b")),
  # Aadhaar: 12 digits, first digit 2-9, optionally grouped 4-4-4 with spaces or hyphens
  ("AADHAAR", re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
  # Bank account: 9-18 digits, only right after "account"/"a/c" (+ "no."/"number").
  # Group 1 keeps that label; only the digits are masked.
  ("ACCOUNT", re.compile(r"(\b(?:a/c|account)\b[^\d\n]{0,20})\d{9,18}(?!\d)", re.IGNORECASE)),
  # Indian mobile: optional +91 or 0, then 10 digits starting 6-9 (5-5 grouping allowed)
  ("PHONE", re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
]


def redact(text: str) -> tuple[str, dict[str, int]]:
  """Return (masked text, {kind: how many were masked}). Kinds with no match are left out."""
  counts = Counter()
  for kind, pattern in PATTERNS:
    marker = f"[{kind}]"
    if kind == "ACCOUNT":
      # keep the "Account No. " label, replace only the digits
      text, n = pattern.subn(lambda match: match.group(1) + marker, text)
    else:
      text, n = pattern.subn(marker, text)
    if n:
      counts[kind] += n
  return text, dict(counts)

