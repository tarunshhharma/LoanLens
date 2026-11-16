"""Tests for app/store.py and hybrid_search, using a real Chroma database in a
temporary folder and a FAKE embedder (no OpenAI calls)."""

import pytest

from app.retrieval import hybrid_search
from app.splitting import CLAUSE, DEFINITION, Chunk
from app.store import (
    add_document,
    get_collection,
    get_document_chunks,
    to_metadata,
    vector_search,
)

VOCAB = ["interest", "penal", "insurance", "law"]


def fake_embed(texts):
    # One dimension per vocabulary word; similar wording -> similar vectors.
    # The trailing 0.01 avoids an all-zero vector, which has no direction.
    return [[text.lower().count(word) for word in VOCAB] + [0.01] for text in texts]


CHUNKS = [
    Chunk(CLAUSE, "5.1", 7, 7, ["Interest shall accrue monthly. Interest is payable."], line_pages=[7]),
    Chunk(DEFINITION, None, 3, 3, ['"Penal Charges" means charges on default'],
          term="Penal Charges", line_pages=[3]),
    Chunk(CLAUSE, "9.2", 12, 13, ["Keep the property under insurance", "at all times"],
          line_pages=[12, 13], part=2),
]


@pytest.fixture
def collection(tmp_path):
    return get_collection(str(tmp_path))  # a fresh database for every test


def test_metadata_leaves_out_none_values():
    metadata = to_metadata(CHUNKS[0], "doc1", "a.pdf")
    assert metadata == {"doc_id": "doc1", "filename": "a.pdf", "kind": CLAUSE,
                        "number": "5.1", "page_start": 7, "page_end": 7}


def test_add_document_stores_every_chunk(collection):
    add_document(collection, "doc1", "a.pdf", CHUNKS, fake_embed)
    stored = get_document_chunks(collection, "doc1")
    assert sorted(stored["ids"]) == ["doc1:0", "doc1:1", "doc1:2"]


def test_reupload_replaces_instead_of_duplicating(collection):
    add_document(collection, "doc1", "a.pdf", CHUNKS, fake_embed)
    add_document(collection, "doc1", "a.pdf", CHUNKS[:1], fake_embed)
    assert get_document_chunks(collection, "doc1")["ids"] == ["doc1:0"]


def test_vector_search_finds_the_similar_chunk(collection):
    add_document(collection, "doc1", "a.pdf", CHUNKS, fake_embed)
    assert vector_search(collection, "doc1", "how is interest charged?", fake_embed, k=1) == ["doc1:0"]


def test_search_only_sees_the_requested_document(collection):
    add_document(collection, "doc1", "a.pdf", CHUNKS[:1], fake_embed)
    add_document(collection, "doc2", "b.pdf", CHUNKS[1:], fake_embed)
    # doc1 holds the best "interest" match, but it must never be returned for doc2
    assert set(vector_search(collection, "doc2", "interest", fake_embed, k=5)) == {"doc2:0", "doc2:1"}


def test_hybrid_search_returns_text_and_metadata(collection):
    add_document(collection, "doc1", "a.pdf", CHUNKS, fake_embed)
    top = hybrid_search(collection, "doc1", "what are the penal charges", fake_embed, top_k=1)
    assert top[0]["id"] == "doc1:1"
    assert top[0]["metadata"]["term"] == "Penal Charges"
    assert top[0]["text"].startswith('"Penal Charges"')


def test_hybrid_search_unknown_document_is_empty(collection):
    assert hybrid_search(collection, "missing", "anything", fake_embed) == []
