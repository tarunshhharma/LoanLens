"""Tests for app/retrieval.py: tokenizer, BM25 and reciprocal rank fusion."""

from app.retrieval import bm25_search, reciprocal_rank_fusion, tokenize

# --- tokenize -----------------------------------------------------------------

def test_tokenize_lowercases_and_drops_punctuation():
    assert tokenize("The Borrower shall pay; INTEREST.") == ["the", "borrower", "shall", "pay", "interest"]


def test_tokenize_keeps_clause_numbers_whole():
    # so "clause 5.1" matches "5.1" and not every chunk containing a 5 or a 1
    assert tokenize("as per clause 5.1 and 1.2.8") == ["as", "per", "clause", "5.1", "and", "1.2.8"]


# --- bm25_search --------------------------------------------------------------

IDS = ["interest", "penal", "insurance", "law"]
DOCS = [
    "Interest on the Loan shall accrue monthly at the applicable rate",
    "Penal Charges are payable on any amount in default",
    "The Borrower shall keep the property insured",
    "This Agreement is governed by Indian law",
]


def test_bm25_ranks_the_matching_chunk_first():
    assert bm25_search(IDS, DOCS, "what are the penal charges?", k=4)[0] == "penal"


def test_bm25_drops_chunks_with_no_matching_word():
    assert bm25_search(IDS, DOCS, "penal charges", k=4) == ["penal"]


def test_bm25_respects_k():
    assert len(bm25_search(IDS, DOCS, "the loan shall be governed by law", k=1)) == 1


def test_bm25_empty_corpus():
    assert bm25_search([], [], "anything", k=5) == []


# --- reciprocal_rank_fusion ---------------------------------------------------

def test_rrf_single_ranking_keeps_order():
    assert reciprocal_rank_fusion([["a", "b", "c"]]) == ["a", "b", "c"]


def test_rrf_item_in_both_lists_beats_item_in_one():
    # "b" is 2nd in both lists: 2/(60+2) beats 1/(60+1) for "a" or "c"
    assert reciprocal_rank_fusion([["a", "b"], ["c", "b"]])[0] == "b"


def test_rrf_uses_the_formula():
    # k=1 makes the numbers easy: a = 1/2 + 1/3, b = 1/3 + 1/2, c = 1/4
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a"]], k=1)
    assert fused == ["a", "b", "c"]  # a and b tie; a was seen first


def test_rrf_includes_items_from_every_list():
    assert set(reciprocal_rank_fusion([["a"], ["b"], ["c"]])) == {"a", "b", "c"}


def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
