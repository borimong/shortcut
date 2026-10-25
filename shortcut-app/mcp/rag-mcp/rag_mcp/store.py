"""문서 chunk와 임베딩 저장소.

- PgVectorStore (compose 기본): shortcut DB의 rag 스키마. 확장(vector)과 스키마는 db/init/00_init.sql이 만든다.
- MemoryStore (개발·테스트): 같은 메서드를 가진 메모리 저장소.

검색 점수는 둘 다 코사인 유사도(1 - 코사인 거리)다.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Protocol

from rag_mcp.chunking import Chunk, Document


class Store(Protocol):
    def upsert(self, document: Document, chunks: list[Chunk], vectors: list[list[float]], model: str) -> None: ...
    def delete(self, doc_id: str) -> bool: ...
    def search(self, vector: list[float], k: int, *, doc_types: list[str] | None = None,
               doc_id: str | None = None) -> list[dict[str, Any]]: ...
    def get_document(self, doc_id: str) -> dict[str, Any] | None: ...
    def list_documents(self) -> list[dict[str, Any]]: ...


class PgVectorStore:
    """rag.documents, rag.chunks 테이블을 다룬다."""

    def __init__(self, dsn: str, dimension: int):
        from pgvector.psycopg import register_vector
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.dimension = dimension
        self._pool = ConnectionPool(
            dsn, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, configure=register_vector, open=True
        )

    def ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag.documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    version TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INT NOT NULL,
                    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS rag.chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL REFERENCES rag.documents(doc_id) ON DELETE CASCADE,
                    chunk_no INT NOT NULL,
                    heading TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector({self.dimension}) NOT NULL
                )
                """
            )
            # 적용 장소는 나중에 더한 열이라, 이미 만들어진 DB에도 붙도록 따로 추가한다.
            conn.execute("ALTER TABLE rag.documents ADD COLUMN IF NOT EXISTS scope JSONB NOT NULL DEFAULT '{}'")
            conn.execute("ALTER TABLE rag.chunks ADD COLUMN IF NOT EXISTS locations TEXT[] NOT NULL DEFAULT '{}'")

    def upsert(self, document: Document, chunks: list[Chunk], vectors: list[list[float]], model: str) -> None:
        """같은 문서를 다시 색인하면 이전 chunk를 지우고 새로 넣는다 (한 트랜잭션)."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM rag.documents WHERE doc_id = %s", (document.doc_id,))
            conn.execute(
                """
                INSERT INTO rag.documents (doc_id, title, doc_type, version, text, embedding_model, embedding_dim, scope)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (document.doc_id, document.title, document.doc_type, document.version, document.text, model,
                 self.dimension, json.dumps(document_scope(document), ensure_ascii=False)),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO rag.chunks (chunk_id, doc_id, chunk_no, heading, text, embedding, locations) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [(c.chunk_id, c.doc_id, c.chunk_no, c.heading, c.text, v, list(c.locations))
                     for c, v in zip(chunks, vectors, strict=True)],
                )

    def delete(self, doc_id: str) -> bool:
        with self._pool.connection() as conn:
            return conn.execute("DELETE FROM rag.documents WHERE doc_id = %s", (doc_id,)).rowcount > 0

    def search(self, vector, k, *, doc_types=None, doc_id=None):
        conditions, params = [], []
        if doc_types:
            conditions.append("d.doc_type = ANY(%s)")
            params.append(doc_types)
        if doc_id:
            conditions.append("d.doc_id = %s")
            params.append(doc_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._pool.connection() as conn:
            return conn.execute(
                f"""
                SELECT c.chunk_id, c.doc_id, d.title, d.doc_type, d.version, c.heading, c.text, c.locations,
                       1 - (c.embedding <=> %s::vector) AS score
                FROM rag.chunks c JOIN rag.documents d ON d.doc_id = c.doc_id
                {where}
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                [vector, *params, vector, k],
            ).fetchall()

    def get_document(self, doc_id):
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT doc_id, title, doc_type, version, text, embedding_model, embedding_dim "
                "FROM rag.documents WHERE doc_id = %s",
                (doc_id,),
            ).fetchone()

    def list_documents(self):
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT d.doc_id, d.title, d.doc_type, d.version, d.embedding_model, d.embedding_dim, d.scope,
                       count(c.chunk_id) AS chunks
                FROM rag.documents d LEFT JOIN rag.chunks c ON c.doc_id = d.doc_id
                GROUP BY d.doc_id ORDER BY d.doc_id
                """
            ).fetchall()


class MemoryStore:
    """PgVectorStore와 같은 메서드를 가진 메모리 저장소. 서버를 다시 띄우면 비므로 indexer를 다시 돌린다."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, tuple[Chunk, list[float]]] = {}

    def ensure_schema(self) -> None:
        return None

    def upsert(self, document, chunks, vectors, model):
        self.delete(document.doc_id)
        self.documents[document.doc_id] = {
            "doc_id": document.doc_id, "title": document.title, "doc_type": document.doc_type,
            "version": document.version, "text": document.text,
            "embedding_model": model, "embedding_dim": len(vectors[0]) if vectors else 0,
            "scope": document_scope(document),
        }
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.chunks[chunk.chunk_id] = (chunk, vector)

    def delete(self, doc_id):
        existed = self.documents.pop(doc_id, None) is not None
        self.chunks = {k: v for k, v in self.chunks.items() if v[0].doc_id != doc_id}
        return existed

    def search(self, vector, k, *, doc_types=None, doc_id=None):
        rows = []
        for chunk, stored in self.chunks.values():
            document = self.documents[chunk.doc_id]
            if doc_types and document["doc_type"] not in doc_types:
                continue
            if doc_id and chunk.doc_id != doc_id:
                continue
            rows.append({**document, "chunk_id": chunk.chunk_id, "heading": chunk.heading, "text": chunk.text,
                         "locations": list(chunk.locations), "score": _cosine(vector, stored)})
        return sorted(rows, key=lambda row: row["score"], reverse=True)[:k]

    def get_document(self, doc_id):
        return self.documents.get(doc_id)

    def list_documents(self):
        counts: dict[str, int] = {}
        for chunk, _ in self.chunks.values():
            counts[chunk.doc_id] = counts.get(chunk.doc_id, 0) + 1
        return [{k: v for k, v in d.items() if k != "text"} | {"chunks": counts.get(d["doc_id"], 0)}
                for d in sorted(self.documents.values(), key=lambda d: d["doc_id"])]


def document_scope(document: Document) -> dict[str, Any]:
    """문서의 적용 장소 정보. indexer가 바뀌었는지 비교할 수 있게 문서 목록에도 싣는다."""
    return {
        "locations": list(document.locations),
        "section_locations": {heading: list(places) for heading, places in document.section_locations.items()},
    }


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def store_from_env(dimension: int) -> Store:
    kind = os.getenv("RAG_STORE", "pgvector").lower()
    if kind == "memory":
        return MemoryStore()
    if kind == "pgvector":
        store = PgVectorStore(os.getenv("RAG_DB_DSN", "postgresql://shortcut:shortcut@localhost:5432/shortcut"), dimension)
        store.ensure_schema()
        return store
    raise ValueError(f"RAG_STORE는 pgvector 또는 memory: {kind}")
