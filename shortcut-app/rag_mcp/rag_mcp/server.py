"""규정, 법규, 계약서 근거 검색을 MCP 도구로 노출하는 서버입니다.

업무 데이터는 다루지 않고 문서 색인과 검색만 맡습니다.
계약서는 온톨로지가 특정한 문서 안에서만 찾도록 일반 규정 검색과 도구를 나눴습니다.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Literal, Protocol

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from rag_mcp.chunking import Document, split_into_chunks

logger = logging.getLogger("rag-mcp")

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}

RegulationType = Literal["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY"]
DocId = Annotated[str, Field(pattern=r"^[a-z0-9\-]+$", max_length=80)]


class Embedder(Protocol):
    model: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Store(Protocol):
    def upsert(self, document, chunks, vectors, model) -> None: ...
    def delete(self, doc_id: str) -> bool: ...
    def search(self, vector, k, *, doc_types=None, doc_id=None) -> list[dict]: ...
    def get_document(self, doc_id: str) -> dict | None: ...
    def list_documents(self) -> list[dict]: ...


def _error_text(code: str, message: str, retryable: bool) -> str:
    # Agent Harness가 정규식으로 code와 retryable을 읽으므로 business-mcp와 같은 형식을 쓴다.
    return f"[{code}] {message} (retryable={'true' if retryable else 'false'})"


def build_server(store: Store, embedder: Embedder) -> FastMCP:
    """저장소와 임베딩 모델을 주입받아 도구와 Resource를 등록합니다."""
    mcp = FastMCP(
        "rag-mcp",
        instructions=(
            "촬영 관련 규정(근로기준법, 촬영 허가, 비행 금지 구역, 재난과 기상 안전 기준, 예산과 승인 규정)과 "
            "배우 계약서 조항을 검색합니다. 결과의 chunk_id를 근거 ID로 인용하세요."
        ),
    )

    def embed_query(query: str) -> list[float]:
        try:
            return embedder.embed([query])[0]
        except Exception as error:
            logger.warning("질의 임베딩 실패: %s", error)
            raise ToolError(_error_text("EMBEDDING_UNAVAILABLE", "임베딩 모델을 호출할 수 없습니다.", True)) from error

    def run_search(vector, k, **filters) -> list[dict]:
        try:
            rows = store.search(vector, k, **filters)
        except Exception as error:
            logger.warning("벡터 검색 실패: %s", error)
            raise ToolError(_error_text("VECTOR_DB_UNAVAILABLE", "벡터 DB 검색에 실패했습니다.", True)) from error
        return [
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "doc_type": row["doc_type"],
                "version": row["version"],
                "heading": row["heading"],
                "text": row["text"],
                "score": round(float(row["score"]), 4),
            }
            for row in rows
        ]

    @mcp.tool(annotations=READ_ONLY)
    def search_regulation(
        query: Annotated[str, Field(min_length=2, max_length=200, description="찾을 내용, 예: 주 52시간 연장 근로 한도")],
        k: Annotated[int, Field(ge=1, le=8)] = 4,
        doc_types: Annotated[
            list[RegulationType] | None,
            Field(
                description="좁힐 문서 종류. LAW 법률, PERMIT 촬영 허가, NO_FLY 비행 금지, SAFETY 재난과 기상, POLICY 예산과 승인"
            ),
        ] = None,
    ) -> list[dict]:
        """법규와 사내 규정에서 질의와 가까운 조항을 찾아 chunk_id, 제목, 조항 제목, 원문, 유사도를 돌려준다.
        계약서는 포함하지 않는다. 계약서 조항은 search_contract_clause를 쓴다."""
        types = list(doc_types) if doc_types else ["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY"]
        return run_search(embed_query(query), k, doc_types=types)

    @mcp.tool(annotations=READ_ONLY)
    def search_contract_clause(
        query: Annotated[str, Field(min_length=2, max_length=200, description="찾을 조항 내용, 예: 야간 촬영 제한")],
        contract_doc_id: Annotated[
            str, Field(pattern=r"^contract-[a-z0-9\-]+$", description="온톨로지에서 확인한 계약서 문서 ID")
        ],
        k: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> list[dict]:
        """지정한 계약서 한 건 안에서만 조항을 찾는다. 다른 배우나 옛 버전 계약서를 근거로 쓰지 않기 위해
        온톨로지가 특정한 계약서 문서 ID(예: contract-actor-a-v3)를 반드시 넘긴다."""
        if store.get_document(contract_doc_id) is None:
            available = [d["doc_id"] for d in store.list_documents() if d["doc_type"] == "CONTRACT"]
            raise ToolError(
                _error_text(
                    "CONTRACT_NOT_FOUND",
                    f"{contract_doc_id} 계약서가 색인에 없습니다. 있는 계약서: {', '.join(available)}",
                    False,
                )
            )
        return run_search(embed_query(query), k, doc_id=contract_doc_id)

    @mcp.tool(annotations=WRITE)
    def index_document(
        doc_id: DocId,
        title: Annotated[str, Field(min_length=1, max_length=200)],
        doc_type: Literal["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY", "CONTRACT"],
        version: Annotated[str, Field(min_length=1, max_length=40)],
        text: Annotated[str, Field(min_length=20)],
    ) -> dict:
        """문서를 조항 단위로 잘라 임베딩하고 저장한다. 같은 doc_id가 있으면 새 내용으로 바꾼다(재색인)."""
        document = Document(doc_id, title, doc_type, version, text)
        chunks = split_into_chunks(document)
        try:
            vectors = embedder.embed([f"{title}\n{c.heading}\n{c.text}" for c in chunks])
        except Exception as error:
            raise ToolError(_error_text("EMBEDDING_UNAVAILABLE", "임베딩 모델을 호출할 수 없습니다.", True)) from error
        store.upsert(document, chunks, vectors, embedder.model)
        return {"doc_id": doc_id, "chunks": len(chunks), "embedding_model": embedder.model, "dimension": embedder.dimension}

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_document(doc_id: DocId) -> dict:
        """문서와 chunk를 색인에서 지운다. 되돌릴 수 없다."""
        if not store.delete(doc_id):
            raise ToolError(_error_text("DOCUMENT_NOT_FOUND", f"{doc_id} 문서가 색인에 없습니다.", False))
        return {"doc_id": doc_id, "deleted": True}

    @mcp.resource("rag://documents/{doc_id}", mime_type="text/markdown")
    def read_document(doc_id: str) -> str:
        """근거 패널이 보여 줄 문서 원문 전체입니다."""
        document = store.get_document(doc_id)
        if document is None:
            raise ToolError(_error_text("DOCUMENT_NOT_FOUND", f"{doc_id} 문서가 색인에 없습니다.", False))
        return f"# {document['title']}\n\n문서 ID {doc_id}, 종류 {document['doc_type']}, 버전 {document['version']}\n\n{document['text']}"

    @mcp.resource("rag://index/info", mime_type="application/json")
    def index_info() -> str:
        """색인 문서 목록과 임베딩 모델 이름, 차원입니다. 질의도 같은 모델로 임베딩해야 하므로 함께 공개한다."""
        return json.dumps(
            {"embedding_model": embedder.model, "dimension": embedder.dimension, "documents": store.list_documents()},
            ensure_ascii=False,
            default=str,
        )

    return mcp


def main() -> None:
    """compose 안에서 Streamable HTTP로 서버를 실행합니다."""
    from rag_mcp.embedding import OpenAIEmbedder
    from rag_mcp.store import PgVectorStore

    logging.basicConfig(level=logging.INFO)
    embedder = OpenAIEmbedder()
    store = PgVectorStore(os.getenv("RAG_DB_DSN", "postgresql://shortcut:shortcut@localhost:5432/shortcut"), embedder.dimension)
    store.ensure_schema()
    server = build_server(store, embedder)
    server.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "9102")), path="/mcp")


if __name__ == "__main__":
    main()
