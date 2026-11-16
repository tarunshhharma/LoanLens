"""Hybrid retrieval: BM25 keyword search + vector search, fused with RRF.

Why both: vectors find meaning ("cost of paying late" -> "Penal Charges"), BM25 finds
exact words embeddings blur ("clause 5.1", "MCLR", "foreclosure"). RRF merges the two
rankings without having to compare their scores, which are on different scales.
"""

import re
from collections import defaultdict
from rank_bm25 import BM25Okapi
from app.store import Embedder, get_document_chunks, vector_search

RRF_K = 60                # standard constant from the RRF paper; dampens the gap between ranks
CANDIDATES = 20           # how many results each retriever contributes before fusion

TOKEN_PATTERN = re.compile(r"\w+(?:\.\w+)*")

def tokenize(text: str) -> list[str]:
  return TOKEN_PATTERN.findall(text.lower())


def bm25_search(ids: list[str], documents: list[str], question: str, k: int) -> list[str]:
  """Return up to k ids ranked by BM25 score. Chunks sharing no word with the question are dropped."""
  if not documents:
    return []
  bm25 = BM25Okapi([tokenize(doc) for doc in documents])
  scores = bm25.get_scores(tokenize(question))
  ranked = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
  return [chunk_id for chunk_id, score in ranked[:k] if score > 0]

def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
  """Merge rankings: each id scores sum(1 / (k + rank)) over the rankings it appears in.

    Ranks start at 1. Ties keep the order in which ids were first seen.
  """
  scores = defaultdict(float)
  for ranking in rankings:
    for rank, item in enumerate(ranking, start=1):
      scores[item] += 1 / (k + rank)
  return sorted(scores, key=lambda item: scores[item], reverse=True)

def hybrid_search(collection, doc_id: str, question:str, embed: Embedder, top_k: int=5) -> list[dict]:
  """Return the top_k chunks for a question: [{"id", "text", "metadata"}, ...]."""
  stored = get_document_chunks(collection, doc_id)
  if not stored["ids"]:
      return []

  by_id = {
    chunk_id: {"id": chunk_id, "text": text, "metadata": metadata}
    for chunk_id, text, metadata in zip(stored["ids"], stored["documents"], stored["metadatas"])
  }
  keyword_ranking = bm25_search(stored["ids"], stored["documents"], question, CANDIDATES)
  vector_ranking = vector_search(collection, doc_id, question, embed, CANDIDATES)

  fused = reciprocal_rank_fusion([vector_ranking, keyword_ranking])
  return [by_id[chunk_id] for chunk_id in fused[:top_k]]