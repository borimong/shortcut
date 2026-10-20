"""Vector 저장소.

지금은 파일 기반 LocalVectorStore(numpy 코사인 유사도)로 시작한다. 외부 서비스가 없어서
바로 돌릴 수 있고, chunk 수백 개 규모에서는 충분히 빠르다.

팀이 Chroma 또는 pgvector로 정하면(아키텍처 문서 미결정 2) 같은 메서드
(save / load / search / get / sections / doc_ids)를 가진 클래스를 하나 더 만들어
retriever.py에서 바꿔 끼우면 된다. 도구 코드는 바뀌지 않는다.

저장 파일:
  <index_dir>/meta.json     embeddingModel, dim, createdAt, chunkCount   ← 교안 필수: 모델 이름·차원 기록
  <index_dir>/chunks.json   chunk 목록
  <index_dir>/vectors.npy   chunk별 벡터 (정규화됨)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .chunker import Chunk


class IndexMismatchError(RuntimeError):
    """색인할 때와 다른 Embedding 모델로 검색하려 할 때."""


class LocalVectorStore:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, meta: dict):
        if len(chunks) != len(vectors):
            raise ValueError("chunk 수와 벡터 수가 다르다")
        self.chunks = chunks
        self.vectors = vectors.astype(np.float32)
        self.meta = meta
        self._by_key = {(c.docId, c.section): c for c in chunks}

    # ------------------------------------------------------------ 저장·불러오기

    @classmethod
    def build(cls, chunks: list[Chunk], embedder) -> "LocalVectorStore":
        vectors = embedder.embed([f"{c.title}\n{c.sectionTitle}\n{c.text}" for c in chunks])
        meta = {
            "embeddingModel": embedder.name,
            "dim": int(embedder.dim),
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chunkCount": len(chunks),
            "docCount": len({c.docId for c in chunks}),
        }
        return cls(chunks, vectors, meta)

    def save(self, index_dir: str | Path) -> None:
        d = Path(index_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "chunks.json").write_text(
            json.dumps([c.to_dict() for c in self.chunks], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        np.save(d / "vectors.npy", self.vectors)

    @classmethod
    def load(cls, index_dir: str | Path, embedder=None) -> "LocalVectorStore":
        d = Path(index_dir)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if embedder is not None and (meta["embeddingModel"] != embedder.name or meta["dim"] != embedder.dim):
            raise IndexMismatchError(
                f"색인 모델 {meta['embeddingModel']}({meta['dim']}차원)과 검색 모델 "
                f"{embedder.name}({embedder.dim}차원)이 다르다. 같은 모델로 다시 색인하라."
            )
        chunks = [Chunk(**c) for c in json.loads((d / "chunks.json").read_text(encoding="utf-8"))]
        return cls(chunks, np.load(d / "vectors.npy"), meta)

    @staticmethod
    def exists(index_dir: str | Path) -> bool:
        d = Path(index_dir)
        return all((d / f).exists() for f in ("meta.json", "chunks.json", "vectors.npy"))

    # ------------------------------------------------------------ 조회

    def _match(self, c: Chunk, where: dict | None) -> bool:
        if not where:
            return True
        for k, v in where.items():
            got = c.docId if k == "docId" else c.meta.get(k)
            if v is not None and got != v:
                return False
        return True

    def search(self, query_vec: np.ndarray, k: int = 5, where: dict | None = None) -> list[tuple[Chunk, float]]:
        idx = [i for i, c in enumerate(self.chunks) if self._match(c, where)]
        if not idx:
            return []
        scores = self.vectors[idx] @ query_vec.astype(np.float32)
        order = np.argsort(-scores)[:k]
        return [(self.chunks[idx[i]], float(scores[i])) for i in order]

    def filter(self, where: dict) -> list[Chunk]:
        return [c for c in self.chunks if self._match(c, where)]

    def get(self, doc_id: str, section: str) -> Chunk | None:
        return self._by_key.get((doc_id, section))

    def sections(self, doc_id: str) -> list[str]:
        return [c.section for c in self.chunks if c.docId == doc_id]

    def doc_ids(self, **where) -> list[str]:
        return sorted({c.docId for c in self.chunks if self._match(c, where)})

    def values(self, key: str) -> list[str]:
        return sorted({str(c.meta[key]) for c in self.chunks if key in c.meta})
