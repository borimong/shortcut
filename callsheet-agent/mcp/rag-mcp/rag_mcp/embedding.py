"""문서와 질의를 같은 모델로 벡터화한다.

- `openai` (기본, compose): text-embedding-3-small, 1536차원
- `hash` (개발·테스트): 단어 해시를 세는 결정적 임베딩. 키 없이 검색 흐름을 확인할 때 쓴다.

색인과 검색은 반드시 같은 모델이어야 한다. 모델 이름은 문서마다 저장되고,
indexer는 모델이 바뀐 문서를 다시 색인한다.
"""
from __future__ import annotations

import hashlib
import os
from typing import Protocol


class Embedder(Protocol):
    model: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """OpenAI 임베딩 API를 호출한다."""

    def __init__(self, model: str | None = None, dimension: int | None = None) -> None:
        from openai import OpenAI

        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIM", "1536"))
        # 일시 오류는 SDK 기본 재시도(2회)에 맡기고, 그래도 실패하면 호출자가 retryable 오류로 바꾼다.
        self._client = OpenAI(timeout=20.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts, dimensions=self.dimension)
        return [item.embedding for item in response.data]


class HashEmbedder:
    """결정적 개발용 임베딩. 의미 검색 품질은 없지만 단어가 겹치면 가깝다."""

    def __init__(self, dimension: int = 256) -> None:
        self.model = f"hash-{dimension}"
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in text.replace("\n", " ").split():
                vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimension] += 1.0
            vectors.append(vector)
        return vectors


def embedder_from_env() -> Embedder:
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
    if provider == "hash":
        return HashEmbedder(int(os.getenv("EMBEDDING_DIM", "256")))
    if provider == "openai":
        return OpenAIEmbedder()
    raise ValueError(f"EMBEDDING_PROVIDER는 openai 또는 hash: {provider}")
