"""Tests for app/redact.py: masking personal data before it is stored or sent to OpenAI.

Run from the project root:
    pytest tests/test_redact.py -v
"""

import io

import pymupdf
import pytest
from fastapi import UploadFile

import app.main as main
from app.redact import redact
from app.store import get_collection, get_document_chunks

# --- Each kind of personal data is masked ---------------------------------------

@pytest.mark.parametrize("text, masked, kind", [
    ("PAN: ABCPE1234F", "PAN: [PAN]", "PAN"),
    ("Aadhaar No. 2345 6789 0123", "Aadhaar No. [AADHAAR]", "AADHAAR"),
    ("Aadhaar: 2345-6789-0123", "Aadhaar: [AADHAAR]", "AADHAAR"),
    ("UID 234567890123 attached", "UID [AADHAAR] attached", "AADHAAR"),
    ("Mobile: 9876543210", "Mobile: [PHONE]", "PHONE"),
    ("Call +91 98765 43210 today", "Call [PHONE] today", "PHONE"),
    ("Tel +91-9876543210.", "Tel [PHONE].", "PHONE"),
    ("Phone 09876543210", "Phone [PHONE]", "PHONE"),
    ("Email: ravi.kumar+loans@example.co.in", "Email: [EMAIL]", "EMAIL"),
    ("Savings Account No. 123456789012345", "Savings Account No. [ACCOUNT]", "ACCOUNT"),
    ("A/c number: 001234567890", "A/c number: [ACCOUNT]", "ACCOUNT"),
])
def test_masks_personal_data(text, masked, kind):
    result, counts = redact(text)
    assert result == masked
    assert counts == {kind: 1}


def test_counts_every_occurrence():
    _, counts = redact("PAN ABCPE1234F, co-borrower PAN XYZPK9876L, mobile 9876543210")
    assert counts == {"PAN": 2, "PHONE": 1}


def test_masks_across_a_multi_line_page():
    page = "Borrower: Ravi Kumar\nPAN: ABCPE1234F\nMobile: 9876543210\n5.1 Interest at 10.5%"
    result, _ = redact(page)
    assert result == "Borrower: Ravi Kumar\nPAN: [PAN]\nMobile: [PHONE]\n5.1 Interest at 10.5%"


# --- Ordinary agreement text is left alone ---------------------------------------

@pytest.mark.parametrize("text", [
    "The loan amount is Rs 5,00,000 (Rupees Five Lakh only).",
    "Rs 120000 at 19.25% per annum",
    "As per clause 1.2.8 and 12.3.4 above",
    "Dated 15/03/2026 at Jaipur",
    "IFSC: HDFC0001234",                          # a branch code, not personal
    "Stamp Ref No: IN-RJ09290509414932X",         # digits inside a longer code
    "Toll-free 1800 123 4567",                    # not a mobile number
    "into the account of the Borrower",           # "account" with no number
    "Reference 12345678",                         # 8 digits: too short for an account
])
def test_leaves_ordinary_text_alone(text):
    result, counts = redact(text)
    assert result == text
    assert counts == {}


def test_bare_ten_digit_number_starting_6_to_9_is_treated_as_a_phone():
    # Deliberate trade-off: masking a rare amount beats leaking a real phone number
    assert redact("Ref 9876543210")[0] == "Ref [PHONE]"


def test_account_numbers_need_context():
    # A long digit run with no "account"/"a/c" nearby is not assumed to be an account
    assert redact("Batch 123456789012345 printed")[1] == {}


def test_redacting_twice_changes_nothing():
    once, _ = redact("PAN ABCPE1234F, mobile 9876543210, ravi@example.com")
    twice, counts = redact(once)
    assert twice == once
    assert counts == {}


# --- /upload: personal data never reaches the store -------------------------------

def make_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 16 * i), line, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def fake_store(tmp_path, monkeypatch):
    collection = get_collection(str(tmp_path))
    monkeypatch.setattr(main, "collection", lambda: collection)
    monkeypatch.setattr(main, "embed_texts", lambda texts: [[1.0, float(len(t) % 5)] for t in texts])
    return collection


def test_upload_stores_only_redacted_text(fake_store):
    pdf = make_pdf([
        "This loan agreement is made between the Bank and the Borrower.",
        "Borrower PAN: ABCPE1234F   Mobile: +91 98765 43210",
        "Email: ravi.kumar@example.com",
    ])
    result = main.upload_pdf(UploadFile(file=io.BytesIO(pdf), filename="filled.pdf"))

    stored = " ".join(get_document_chunks(fake_store, result["doc_id"])["documents"])
    assert "ABCPE1234F" not in stored and "98765 43210" not in stored
    assert "ravi.kumar@example.com" not in stored
    assert "[PAN]" in stored and "[PHONE]" in stored and "[EMAIL]" in stored
    assert result["redactions"] == {"PAN": 1, "PHONE": 1, "EMAIL": 1}


def test_upload_response_never_echoes_personal_data(fake_store):
    pdf = make_pdf(["This loan agreement is made between the Bank and the Borrower.",
                    "Borrower PAN: ABCPE1234F"])
    result = main.upload_pdf(UploadFile(file=io.BytesIO(pdf), filename="filled.pdf"))
    assert "ABCPE1234F" not in str(result)
