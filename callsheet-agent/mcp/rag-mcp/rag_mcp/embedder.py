"""Embedding 모델.

- openai: 실제 사용. EMBEDDING_PROVIDER=openai, OPENAI_API_KEY 필요.
- hash:   개발·테스트용. 외부 호출 없이 글자 n-gram을 해시해 벡터로 만든다. 키가 없어도 돈다.

색인할 때와 검색할 때 반드시 같은 모델을 써야 한다. 그래서 name과 dim을 색인 메타데이터에
저장하고, 검색 서버가 시작할 때 비교한다 (store.py).
"""
from __future__ import annotations

import hashlib
import os
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    """글자 2~3-gram 해시 벡터. 한국어도 띄어쓰기와 관계없이 겹치는 글자로 비슷함을 잡는다."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hash-ngram-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        t = "".join(text.lower().split())
        for n in (2, 3):
            for i in range(len(t) - n + 1):
                h = int.from_bytes(hashlib.md5(t[i : i + n].encode()).digest()[:4], "little")
                v[h % self.dim] += 1.0
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


class OpenAIEmbedder:
    """OpenAI Embeddings API를 HTTP로 직접 호출한다 (추가 SDK 불필요)."""

    DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dim = self.DIMS.get(self.model, int(os.environ.get("EMBEDDING_DIM", "1536")))
        self.name = f"openai:{self.model}"
        self.api_key = os.environ["OPENAI_API_KEY"]

    def embed(self, texts: list[str]) -> np.ndarray:
        try:
            import httpx
        except ImportError:  # pragma: no cover
            import httpx2 as httpx  # type: ignore[no-redef]

        out: list[list[float]] = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), 64):
                resp = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts[i : i + 64]},
                )
                resp.raise_for_status()
                out.extend(d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"]))
        arr = np.asarray(out, dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)


def get_embedder() -> Embedder:
    provider = os.environ.get("EMBEDDING_PROVIDER", "hash").lower()
    if provider == "openai":
        return OpenAIEmbedder()
    if provider == "hash":
        return HashEmbedder(int(os.environ.get("EMBEDDING_DIM", "512")))
    raise ValueError(f"알 수 없는 EMBEDDING_PROVIDER: {provider} (openai | hash)")
