"""HTTP-level tests for the API, through FastAPI's TestClient.

TestClient sends real HTTP requests to the app in memory (no server, no port), so these
cover what calling the endpoint functions directly skips: multipart file parsing, JSON
bodies, Pydantic's automatic 422s and the status codes a client actually receives.
The model, embedder and database are replaced with fakes: no OpenAI calls, no chroma_db/.

Run from the project root:
    pytest tests/test_api.py -v
"""

import json

import openai
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.store import get_collection

FIXTURES = "tests/fixtures"


def fake_embed(texts):
    return [[float(len(text) % 7 + 1), float(text.count(" ") % 5 + 1)] for text in texts]


def fake_model(system, user):
    """Answers every question from source [1]; extracts nothing."""
    if "Extract these fields" in user:
        return "{}"
    return json.dumps({"answer": "It is stated in the agreement.", "sources": [1]})


@pytest.fixture
def client(tmp_path, monkeypatch):
    collection = get_collection(str(tmp_path))
    monkeypatch.setattr(main, "collection", lambda: collection)
    monkeypatch.setattr(main, "embed_texts", fake_embed)
    monkeypatch.setattr(main, "complete_json", fake_model)
    return TestClient(main.app)


def upload(client, name, content=None, content_type="application/pdf"):
    if content is None:
        with open(f"{FIXTURES}/{name}", "rb") as f:
            content = f.read()
    return client.post("/upload", files={"file": (name, content, content_type)})


# --- /health ------------------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_openai_key(client, monkeypatch):
    # Docker and the hosting platform call /health constantly; it must never touch OpenAI
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert client.get("/health").status_code == 200


# --- /upload ------------------------------------------------------------------------

def test_upload_text_pdf(client):
    response = upload(client, "text.pdf")
    assert response.status_code == 200
    body = response.json()
    assert response.headers["content-type"] == "application/json"
    assert len(body["doc_id"]) == 16
    assert body["chunk_count"] == len(body["chunks"]) > 0
    assert set(body) >= {"filename", "total_pages", "pages", "warnings", "redactions",
                         "numbering_style", "chunks"}


def test_same_file_gets_the_same_doc_id(client):
    assert upload(client, "text.pdf").json()["doc_id"] == upload(client, "text.pdf").json()["doc_id"]


@pytest.mark.parametrize("name, status", [
    ("not_a_pdf.pdf", 400),   # fails the %PDF- signature check
    ("corrupted.pdf", 400),   # signature ok, but PyMuPDF can't parse it
    ("scanned.pdf", 422),     # valid PDF, no extractable text
])
def test_upload_rejects_bad_files(client, name, status):
    response = upload(client, name)
    assert response.status_code == status
    assert response.json()["detail"]  # a human-readable reason


def test_upload_rejects_files_over_20_mb(client):
    too_big = b"%PDF-" + b"0" * (main.MAX_FILE_SIZE + 1)
    assert upload(client, "big.pdf", content=too_big).status_code == 413


def test_upload_without_a_file_is_422(client):
    response = client.post("/upload")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]


def test_upload_warns_about_partly_scanned_pdfs(client):
    response = upload(client, "mixed.pdf")
    assert response.status_code == 200
    assert any("no extractable text" in w for w in response.json()["warnings"])


# --- /ask ---------------------------------------------------------------------------

def test_ask_answers_with_citations(client):
    doc_id = upload(client, "text.pdf").json()["doc_id"]
    response = client.post("/ask", json={"doc_id": doc_id, "question": "What is the loan amount?"})
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["citations"][0]["page_start"] >= 1
    assert body["question"] == "What is the loan amount?"


def test_ask_unknown_document_is_404(client):
    response = client.post("/ask", json={"doc_id": "never-uploaded", "question": "What is the rate?"})
    assert response.status_code == 404


@pytest.mark.parametrize("body, missing_or_bad", [
    ({"doc_id": "x", "question": "hi"}, "question"),      # under 3 characters
    ({"doc_id": "x", "question": "x" * 1001}, "question"),  # over 1000 characters
    ({"question": "What is the rate?"}, "doc_id"),         # field missing
])
def test_ask_validates_its_body(client, body, missing_or_bad):
    response = client.post("/ask", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", missing_or_bad]


def test_ask_rejects_a_non_json_body(client):
    response = client.post("/ask", content=b"question=hello", headers={"content-type": "text/plain"})
    assert response.status_code == 422


def test_ask_model_failure_is_502(client, monkeypatch):
    doc_id = upload(client, "text.pdf").json()["doc_id"]

    def broken(system, user):
        raise openai.OpenAIError("service unavailable")

    monkeypatch.setattr(main, "complete_json", broken)
    response = client.post("/ask", json={"doc_id": doc_id, "question": "What is the rate?"})
    assert response.status_code == 502


# --- /extract -----------------------------------------------------------------------

def test_extract_returns_terms_and_flags(client):
    doc_id = upload(client, "text.pdf").json()["doc_id"]
    response = client.post("/extract", json={"doc_id": doc_id})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"doc_id", "found", "terms", "risk_flags", "warnings"}
    assert body["found"] == []  # the fake model extracts nothing


def test_extract_unknown_document_is_404(client):
    assert client.post("/extract", json={"doc_id": "never-uploaded"}).status_code == 404


# --- Unknown routes and methods -----------------------------------------------------

def test_unknown_route_is_404(client):
    assert client.get("/nope").status_code == 404


def test_wrong_method_is_405(client):
    assert client.get("/ask").status_code == 405
