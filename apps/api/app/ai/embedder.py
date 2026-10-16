"""Embedder interface for Phase 3 - turns code-list/example-memory text into vectors
for pgvector similarity search. One real provider (OllamaEmbedder, bge-m3 served
locally - decided 2026-10-13, see CLAUDE.md), plus FakeEmbedder for deterministic
tests per the plan's own instruction ("Tests with a fake embedder").

Unlike jev (app/ai/jev.py), there's no stub-vs-real split here: Ollama is fully
ours to run, not a third party we're waiting on credentials for, so get_embedder()
always returns the real client.
"""

import hashlib

import httpx
from sqlalchemy.orm import Session

from app.core.settings_store import get_ollama_connection


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
        return response.json()["embeddings"]


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


def get_embedder(db: Session) -> OllamaEmbedder:
    # DB-backed, not just apps/api/.env - this repo is published without the
    # author's own local Ollama instance, so a fresh clone configures its own
    # connection from Admin > LLM Connectivity (app/core/settings_store.py).
    connection = get_ollama_connection(db)
    return OllamaEmbedder(connection.base_url, connection.embedding_model)
