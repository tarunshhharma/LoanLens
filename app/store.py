"""Store chunks and their embeddings in Chroma, and run vector search.

One collection holds every uploaded document. Each chunk's metadata carries the
doc_id, so searches are filtered to the document being asked about.
"""

from collections.abc import Callable
import chromadb
from app.splitting import Chunk

COLLECTION_NAME = "chunks"
DB_PATH = "chroma_db"

Embedder = Callable[[list[str]], list[list[float]]]

def get_collection(path: str=DB_PATH):
  client = chromadb.PersistentClient(path=path)   # saved to disk; survives restarts
  return client.get_or_create_collection(
    COLLECTION_NAME,
    embedding_function=None,
    configuration= {"hnsw": {"space": "cosine"}}
  )

def chunk_id(doc_id: str, index: int) -> str:
  return f"{doc_id}:{index}"

def to_metadata(chunk: Chunk, doc_id: str, filename: str) -> dict:
  """Chunk -> Chroma metadata. Chroma rejects None values, so missing fields are left out."""
  metadata = {
    "doc_id": doc_id,
    "filename": filename,
    "kind": chunk.kind,
    "number": chunk.number,
    "term": chunk.term,
    "part": chunk.part,
    "title": chunk.title,
    "page_start": chunk.page_start,
    "page_end": chunk.page_end,
  }
  return {key: value for key, value in metadata.items() if value is not None}

def add_document(collection, doc_id: str, filename: str, chunks: list[Chunk], embed: Embedder) -> None:
  """Embed and store a document's chunks. Uploading the same document again replaces it."""
  collection.delete(where={"doc_id": doc_id})
  if not chunks:
    return
  texts = [chunk.text for chunk in chunks]
  collection.add(
    ids=[chunk_id(doc_id, i) for i in range(len(chunks))],
    documents=texts,
    embeddings=embed(texts),
    metadatas=[to_metadata(chunk, doc_id, filename) for chunk in chunks],
  )

def get_document_chunks(collection, doc_id: str) -> dict:
  """All chunks of one document: {"ids": [...], "documents": [...], "metadatas": [...]}."""
  return collection.get(where={"doc_id": doc_id})

def vector_search(collection, doc_id: str, question: str, embed: Embedder, k:int) -> list[str]:
  """Return up to k chunk ids of this document, most similar to the question first."""
  result = collection.query(
    query_embeddings=embed([question]),
    n_results=k,
    where={"doc_id": doc_id},
  )
  return result["ids"][0]  # one list per query embedding; we sent one