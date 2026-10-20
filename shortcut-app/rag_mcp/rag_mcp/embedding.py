"""문서와 질의를 같은 모델로 벡터화합니다."""

from __future__ import annotations

import os

from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
# text-embedding-3-small의 기본 차원이다. 색인 메타데이터에 함께 저장해 질의 때 같은 차원인지 확인한다.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))


class OpenAIEmbedder:
    """OpenAI 임베딩 API를 호출합니다."""

    model = EMBEDDING_MODEL
    dimension = EMBEDDING_DIM

    def __init__(self) -> None:
        # 색인은 오프라인 작업이라 일시 오류를 SDK 기본 재시도(2회)로 넘기고, 그래도 실패하면 호출자에게 알린다.
        self._client = OpenAI(timeout=20.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """문장 목록을 같은 순서의 벡터 목록으로 바꿉니다."""
        response = self._client.embeddings.create(model=self.model, input=texts, dimensions=self.dimension)
        return [item.embedding for item in response.data]
