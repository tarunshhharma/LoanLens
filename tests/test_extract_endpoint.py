"""Tests for the /extract endpoint in app/main.py.

The endpoint function is called directly. monkeypatch swaps main.py's real
Chroma, embedder and model for fakes, so no OpenAI calls and no chroma_db/ files.

Run from the project root:
    pytest tests/test_extract_endpoint.py -v
"""

import json

import openai
import pytest
from fastapi import HTTPException

import app.main as main
from app.main import ExtractRequest
from app.splitting import CLAUSE, Chunk
from app.store import add_document, get_collection

VOCAB = ["interest", "penal", "fee", "rate"]


def fake_embed(texts):
    return [[text.lower().count(word) for word in VOCAB] + [0.01] for text in texts]


CHUNKS = [
    Chunk(CLAUSE, "5.1", 7, 7, ["5.1 Interest at 10.5% per annum, floating rate"], line_pages=[7]),
    Chunk(CLAUSE, "9.1", 12, 12, ["9.1 Penal charges of 2% per month on overdue EMI"],
          line_pages=[12]),
]


def model_answering(answers: dict, calls: list):
    """A fake complete_json: answers only the fields its prompt asks for."""
    def complete(system, user):
        calls.append(user)
        return json.dumps({name: value for name, value in answers.items() if f"- {name}:" in user})
    return complete


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    collection = get_collection(str(tmp_path))
    add_document(collection, "doc1", "a.pdf", CHUNKS, fake_embed)
    monkeypatch.setattr(main, "collection", lambda: collection)
    monkeypatch.setattr(main, "embed_texts", fake_embed)
    return monkeypatch


def source_of(text_start: str, user_prompt: str) -> int:
    """Find which [n] the fake search put a chunk at, so the fake model can cite it."""
    for line in user_prompt.splitlines():
        if line.startswith("[") and "]" in line:
            number = int(line[1:line.index("]")])
        elif line.startswith(text_start):
            return number
    raise AssertionError(f"{text_start!r} not in prompt")


def test_returns_cited_terms(fakes):
    calls = []

    def complete(system, user):
        calls.append(user)
        reply = {}
        if "- interest_rate:" in user:
            n = source_of("5.1 Interest", user)
            reply = {"interest_rate": {"value": 10.5, "source": n},
                     "rate_type": {"value": "floating", "source": n}}
        return json.dumps(reply)

    fakes.setattr(main, "complete_json", complete)
    result = main.extract(ExtractRequest(doc_id="doc1"))

    assert result["doc_id"] == "doc1"
    assert result["found"] == ["interest_rate", "rate_type"]
    assert result["terms"]["interest_rate"] == {
        "value": 10.5,
        "citation": {"label": "Clause 5.1, page 7", "page_start": 7, "page_end": 7},
    }
    assert result["terms"]["loan_amount"] is None
    assert result["warnings"] == []


def test_response_is_plain_json(fakes):
    fakes.setattr(main, "complete_json", model_answering({}, []))
    result = main.extract(ExtractRequest(doc_id="doc1"))
    json.dumps(result)  # raises if a Pydantic object leaked into the response


def test_invalid_value_is_dropped_with_a_warning(fakes):
    calls = []

    def complete(system, user):
        calls.append(user)
        if "- interest_rate:" in user:
            return json.dumps({"interest_rate": {"value": 60, "source": 1}})
        return "{}"

    fakes.setattr(main, "complete_json", complete)
    result = main.extract(ExtractRequest(doc_id="doc1"))
    assert result["terms"]["interest_rate"] is None
    assert any("interest_rate" in w for w in result["warnings"])


def test_returns_risk_flags_most_severe_first(fakes):
    fakes.setattr(main, "complete_json", model_answering({
        "rate_type": {"value": "floating", "source": 1},
        "prepayment_charge_applies": {"value": True, "source": 1},
        "interest_rate": {"value": 19.25, "source": 1},
    }, []))
    result = main.extract(ExtractRequest(doc_id="doc1"))
    flags = result["risk_flags"]
    assert [f["rule"] for f in flags] == ["floating_rate_prepayment_charge", "high_interest_rate"]
    assert flags[0]["severity"] == "high"
    assert flags[0]["citations"][0]["page_start"] in (7, 12)
    json.dumps(result)


def test_unknown_doc_id_is_404_without_calling_the_model(fakes):
    calls = []
    fakes.setattr(main, "complete_json", model_answering({}, calls))
    with pytest.raises(HTTPException) as error:
        main.extract(ExtractRequest(doc_id="never-uploaded"))
    assert error.value.status_code == 404
    assert calls == []


def test_openai_failure_is_502(fakes):
    def broken(system, user):
        raise openai.OpenAIError("service unavailable")

    fakes.setattr(main, "complete_json", broken)
    with pytest.raises(HTTPException) as error:
        main.extract(ExtractRequest(doc_id="doc1"))
    assert error.value.status_code == 502
