"""pgvector에 문서 chunk와 임베딩을 저장하고 코사인 유사도로 검색합니다."""

from __future__ import annotations

from typing import Any

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from rag_mcp.chunking import Chunk, Document


class PgVectorStore:
    """rag 스키마의 documents, chunks 테이블을 다룹니다."""

    def __init__(self, dsn: str, dimension: int):
        self.dimension = dimension
        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
            configure=register_vector,
            open=True,
        )

    def ensure_schema(self) -> None:
        """테이블이 없으면 만듭니다. 확장과 스키마는 DB 초기화 스크립트가 미리 만든다."""
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

    def upsert(self, document: Document, chunks: list[Chunk], vectors: list[list[float]], model: str) -> None:
        """같은 문서를 다시 색인하면 이전 chunk를 지우고 새로 넣습니다."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM rag.documents WHERE doc_id = %s", (document.doc_id,))
            conn.execute(
                """
                INSERT INTO rag.documents (doc_id, title, doc_type, version, text, embedding_model, embedding_dim)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (document.doc_id, document.title, document.doc_type, document.version, document.text, model, self.dimension),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO rag.chunks (chunk_id, doc_id, chunk_no, heading, text, embedding) VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        (c.chunk_id, c.doc_id, c.chunk_no, c.heading, c.text, vector)
                        for c, vector in zip(chunks, vectors, strict=True)
                    ],
                )

    def delete(self, doc_id: str) -> bool:
        """문서와 chunk를 지우고 실제로 지웠는지 돌려줍니다."""
        with self._pool.connection() as conn:
            return conn.execute("DELETE FROM rag.documents WHERE doc_id = %s", (doc_id,)).rowcount > 0

    def search(
        self, vector: list[float], k: int, *, doc_types: list[str] | None = None, doc_id: str | None = None
    ) -> list[dict[str, Any]]:
        """질의 벡터와 가까운 chunk를 점수(1 - 코사인 거리) 순으로 돌려줍니다."""
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
                SELECT c.chunk_id, c.doc_id, d.title, d.doc_type, d.version, c.heading, c.text,
                       1 - (c.embedding <=> %s::vector) AS score
                FROM rag.chunks c JOIN rag.documents d ON d.doc_id = c.doc_id
                {where}
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                [vector, *params, vector, k],
            ).fetchall()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """원문 전체와 메타데이터를 돌려줍니다."""
        with self._pool.connection() as conn:
            return conn.execute(
                "SELECT doc_id, title, doc_type, version, text, embedding_model, embedding_dim FROM rag.documents WHERE doc_id = %s",
                (doc_id,),
            ).fetchone()

    def list_documents(self) -> list[dict[str, Any]]:
        """색인된 문서 목록과 chunk 수를 돌려줍니다."""
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT d.doc_id, d.title, d.doc_type, d.version, d.embedding_model, d.embedding_dim,
                       count(c.chunk_id) AS chunks
                FROM rag.documents d LEFT JOIN rag.chunks c ON c.doc_id = d.doc_id
                GROUP BY d.doc_id ORDER BY d.doc_id
                """
            ).fetchall()
