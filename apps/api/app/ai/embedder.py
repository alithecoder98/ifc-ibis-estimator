"""Embedder interface for Phase 3 - turns code-list/example-memory text into vectors
for pgvector similarity search. Two real providers (OllamaEmbedder - bge-m3 served
locally, decided 2026-10-13; OpenAICompatibleEmbedder - any provider speaking the
OpenAI embeddings API shape, added once this repo started being used outside the
author's own machine), plus FakeEmbedder for deterministic tests per the plan's own
instruction ("Tests with a fake embedder").

Unlike jev (app/ai/jev.py), there's no stub-vs-real split here: whichever provider is
configured is fully reachable, not a third party waiting on credentials, so
get_embedder() always returns a real client.
"""

import hashlib

import httpx
from sqlalchemy.orm import Session

from app.core.constants import EMBEDDING_DIM
from app.core.settings_store import get_llm_connection


def _check_dims(vectors: list[list[float]], model: str) -> list[list[float]]:
    # code_list.embedding/example_memory.embedding are a fixed-width pgvector(1024)
    # column (app/core/constants.py) - any model whose output dimension doesn't
    # match fails the very next INSERT with an opaque Postgres error. Switching
    # embedding models (which this module now makes easy to do from the UI) is
    # exactly the scenario this would silently break, so check eagerly and say
    # plainly what's wrong instead.
    for vector in vectors:
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding model {model!r} returned {len(vector)}-dimensional "
                f"vectors, but this database's embedding column is fixed at "
                f"{EMBEDDING_DIM} dimensions. Pick a model with matching output "
                f"size, or this feature needs a migration to change first."
            )
    return vectors


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=120.0,
        )
        response.raise_for_status()
        return _check_dims(response.json()["embeddings"], self.model)


class OpenAICompatibleEmbedder:
    """Any provider speaking the OpenAI embeddings API shape: OpenAI itself,
    OpenRouter, Groq, Together, or a local server like LM Studio/vLLM that mimics
    it. base_url is the API root including version, e.g. "https://api.openai.com/v1"
    - this just appends "/embeddings", same as OpenAI's own client does.
    """

    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
            headers=headers,
            timeout=120.0,
        )
        response.raise_for_status()
        # The API doesn't guarantee response order matches input order (OpenAI's
        # own docs note this) - each item carries its own "index" back.
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        return _check_dims([item["embedding"] for item in items], self.model)


class FakeEmbedder:
    """Deterministic, dependency-free bag-of-words hashing: each word hashes to its
    own pseudo-random vector, and a text's embedding is the sum of its words'
    vectors. Texts sharing words land closer together (higher cosine similarity)
    than texts that share none, so similarity-search tests can assert real rankings
    without needing a running Ollama instance - unlike hashing the whole text at
    once, which would scatter even near-duplicate texts randomly.
    """

    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            for i in range(self.dim):
                vector[i] += digest[i % len(digest)] / 255 - 0.5
        return vector


def get_embedder(db: Session) -> OllamaEmbedder | OpenAICompatibleEmbedder:
    # DB-backed, not just apps/api/.env - this repo is published without the
    # author's own local Ollama instance, so a fresh clone configures its own
    # connection from Admin > LLM Connectivity (app/core/settings_store.py).
    connection = get_llm_connection(db)
    if connection.provider == "openai_compatible":
        return OpenAICompatibleEmbedder(
            connection.base_url, connection.embedding_model, connection.api_key
        )
    return OllamaEmbedder(connection.base_url, connection.embedding_model)
