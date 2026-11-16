import os
from functools import lru_cache

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHAT_MODEL = "gpt-4.1-mini"


EMBED_BATCH_SIZE = 100


@lru_cache(maxsize=1)
def _client() -> OpenAI:
  return OpenAI()


def embed_texts(texts: list[str]) -> list[list[float]]:
  vectors = []
  for start in range(0, len(texts), EMBED_BATCH_SIZE):
    batch = texts[start:start + EMBED_BATCH_SIZE]
    response = _client().embeddings.create(model=EMBEDDING_MODEL, input=batch)
    vectors.extend(item.embedding for item in response.data)
  return vectors

def complete_json(system: str, user:str) -> str:
  response = _client().chat.completions.create(
    model=os.getenv("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL),
    temperature=0,
    response_format={"type": "json_object"},
    messages=[
      {"role": "system", "content": system},
      {"role": "user", "content": user}
    ],
  )
  return response.choices[0].message.content

