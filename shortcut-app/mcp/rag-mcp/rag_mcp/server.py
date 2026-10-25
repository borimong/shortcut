"""rag-mcp: 규정·법규·계약서 근거 검색을 MCP 도구와 Resource로 공개한다.

업무 데이터는 다루지 않고 문서 색인과 검색만 맡는다.
계약서는 온톨로지가 특정한 문서 안에서만 찾도록 일반 규정 검색과 도구를 나눴다
(다른 배우나 옛 버전 계약서가 근거로 섞이지 않게).

도구 4개   search_regulation, search_contract_clause (조회) · index_document (쓰기) · delete_document (삭제)
Resource   rag://documents/{doc_id} (원문, 근거 패널) · rag://index/info (색인 목록, 임베딩 모델)

실행:  python -m rag_mcp.server        → http://0.0.0.0:9102/mcp (Streamable HTTP)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from rag_mcp.chunking import Document, split_into_chunks, split_places
from rag_mcp.embedding import Embedder
from rag_mcp.store import Store

logger = logging.getLogger("rag-mcp")

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

REGULATION_TYPES = ["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY"]
RegulationType = Literal["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY"]
DocId = Annotated[str, Field(pattern=r"^[a-z0-9\-]+$", max_length=80)]
SceneCode = Annotated[str, Field(pattern=r"^S\d{1,3}$", description="씬 코드, 예: S12")]
# 대본 문서는 씬마다 "S#12. 장소 (낮, 실외)" 머리말로 잘린다. 대본 한 편의 씬 수보다 넉넉하게 잡는다.
MAX_SCRIPT_CHUNKS = 200


def format_error(code: str, message: str, retryable: bool) -> str:
    # Agent Harness가 정규식으로 code와 retryable을 읽으므로 business-mcp와 같은 형식을 쓴다.
    return f"[{code}] {message} (retryable={'true' if retryable else 'false'})"


def build_server(store: Store, embedder: Embedder) -> FastMCP:
    """저장소와 임베딩 모델을 주입받아 도구와 Resource를 등록한다."""
    mcp = FastMCP(
        "rag-mcp",
        instructions=(
            "촬영 관련 규정(근로기준법, 촬영 허가, 비행 금지 구역, 재난과 기상 안전 기준, 예산과 승인 규정), "
            "배우 계약서 조항, 대본 씬 원문을 검색합니다. 결과의 chunk_id를 근거 ID로 인용하세요."
        ),
    )

    def embed_query(query: str) -> list[float]:
        try:
            return embedder.embed([query])[0]
        except Exception as error:
            logger.warning("질의 임베딩 실패: %s", error)
            raise ToolError(format_error("EMBEDDING_UNAVAILABLE", "임베딩 모델을 호출할 수 없습니다. 잠시 뒤 다시 시도하세요.", True)) from error

    def run_search(vector: list[float], k: int, **filters) -> list[dict]:
        try:
            rows = store.search(vector, k, **filters)
        except Exception as error:
            logger.warning("벡터 검색 실패: %s", error)
            raise ToolError(format_error("VECTOR_DB_UNAVAILABLE", "벡터 DB 검색에 실패했습니다. 잠시 뒤 다시 시도하세요.", True)) from error
        return [
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "doc_type": row["doc_type"],
                "version": row["version"],
                "heading": row["heading"],
                "text": row["text"],
                # 비어 있으면 어디에나 적용되는 조항이다. Agent가 후보 장소와 맞지 않는 조항을 근거에서 뺀다.
                "locations": list(row.get("locations") or []),
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
            Field(description="좁힐 문서 종류. LAW 법률, PERMIT 촬영 허가, NO_FLY 비행 금지, SAFETY 재난과 기상, POLICY 예산과 승인"),
        ] = None,
    ) -> list[dict]:
        """법규와 사내 규정에서 질의와 가까운 조항을 찾아 chunk_id, 제목, 조항 제목, 원문, 적용 장소, 유사도를 돌려준다.
        특정 장소의 허가 조건이나 비행 금지 구역을 찾을 때는 질의에 장소 이름을 넣는다.
        계약서와 대본은 포함하지 않는다. 계약서 조항은 search_contract_clause, 대본 씬은 search_script를 쓴다."""
        types = list(doc_types) if doc_types else REGULATION_TYPES
        return run_search(embed_query(query), k, doc_types=types)

    @mcp.tool(annotations=READ_ONLY)
    def search_contract_clause(
        query: Annotated[str, Field(min_length=2, max_length=200, description="찾을 조항 내용, 예: 야간 촬영 제한")],
        contract_doc_id: Annotated[
            str, Field(pattern=r"^contract-[a-z0-9\-]+$", description="온톨로지에서 확인한 현재 계약서 문서 ID")
        ],
        k: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> list[dict]:
        """지정한 계약서 한 건 안에서만 조항을 찾는다. 다른 배우나 옛 버전 계약서를 근거로 쓰지 않도록
        get_entity_context로 확인한 계약서 문서 ID(예: contract-actor-a-v3)를 반드시 넘긴다."""
        if store.get_document(contract_doc_id) is None:
            available = [d["doc_id"] for d in store.list_documents() if d["doc_type"] == "CONTRACT"]
            raise ToolError(format_error(
                "CONTRACT_NOT_FOUND",
                f"{contract_doc_id} 계약서가 색인에 없습니다. 있는 계약서: {', '.join(available) or '없음'}. "
                "get_entity_context로 배우의 현재 계약서 ID를 다시 확인하세요.",
                False,
            ))
        return run_search(embed_query(query), k, doc_id=contract_doc_id)

    @mcp.tool(annotations=READ_ONLY)
    def search_script(
        query: Annotated[str, Field(min_length=2, max_length=200, description="찾을 내용, 예: 한강 산책 장면의 낮밤과 장소")],
        scene_codes: Annotated[
            list[SceneCode] | None, Field(max_length=10, description="씬 코드를 주면 그 씬 원문만 씬 순서대로 돌려준다")
        ] = None,
        k: Annotated[int, Field(ge=1, le=8)] = 4,
    ) -> list[dict]:
        """대본(SCRIPT 문서)에서 씬 원문을 찾는다. 씬 머리말(heading)에 극 중 장소, 낮/밤, 실내/실외가 있다.
        영향 받는 씬의 대본 요구(야외 장면인지, 밤 장면인지, 누가 나오는지)를 근거로 인용할 때 쓴다."""
        if not scene_codes:
            return run_search(embed_query(query), k, doc_types=["SCRIPT"])
        hits = run_search(embed_query(query), MAX_SCRIPT_CHUNKS, doc_types=["SCRIPT"])
        order = {f"S#{int(code[1:]):02d}.": i for i, code in enumerate(scene_codes)}
        picked = [hit for hit in hits if hit["heading"].split(" ", 1)[0] in order]
        return sorted(picked, key=lambda hit: (order[hit["heading"].split(" ", 1)[0]], hit["chunk_id"]))

    @mcp.tool(annotations=WRITE)
    def index_document(
        doc_id: DocId,
        title: Annotated[str, Field(min_length=1, max_length=200)],
        doc_type: Literal["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY", "CONTRACT", "SCRIPT"],
        version: Annotated[str, Field(min_length=1, max_length=40)],
        text: Annotated[str, Field(min_length=20)],
        locations: Annotated[
            list[str] | None, Field(description="특정 장소에만 적용되는 문서면 장소 이름 키워드, 예: [\"한강\"]")
        ] = None,
        section_locations: Annotated[
            dict[str, list[str]] | None, Field(description="일부 조항만 다른 장소에 적용될 때 조항 제목 -> 장소 키워드")
        ] = None,
    ) -> dict:
        """문서를 조항 단위로 잘라 임베딩하고 저장한다. 같은 doc_id가 있으면 새 내용으로 바꾼다(재색인)."""
        sections = {heading: split_places(places) for heading, places in (section_locations or {}).items()}
        document = Document(doc_id, title, doc_type, version, text, split_places(locations or []), sections)
        chunks = split_into_chunks(document)
        if not chunks:
            raise ToolError(format_error("EMPTY_DOCUMENT", "본문에 색인할 내용이 없습니다.", False))
        try:
            vectors = embedder.embed([f"{title}\n{c.heading}\n{c.text}" for c in chunks])
        except Exception as error:
            raise ToolError(format_error("EMBEDDING_UNAVAILABLE", "임베딩 모델을 호출할 수 없습니다.", True)) from error
        store.upsert(document, chunks, vectors, embedder.model)
        return {"doc_id": doc_id, "chunks": len(chunks), "embedding_model": embedder.model, "dimension": embedder.dimension}

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_document(doc_id: DocId) -> dict:
        """문서와 chunk를 색인에서 지운다. 되돌릴 수 없다."""
        if not store.delete(doc_id):
            raise ToolError(format_error("DOCUMENT_NOT_FOUND", f"{doc_id} 문서가 색인에 없습니다.", False))
        return {"doc_id": doc_id, "deleted": True}

    @mcp.resource("rag://documents/{doc_id}", mime_type="text/markdown")
    def read_document(doc_id: str) -> str:
        """근거 패널이 보여 줄 문서 원문 전체."""
        document = store.get_document(doc_id)
        if document is None:
            raise ResourceError(format_error("DOCUMENT_NOT_FOUND", f"{doc_id} 문서가 색인에 없습니다.", False))
        return (
            f"# {document['title']}\n\n문서 ID {doc_id}, 종류 {document['doc_type']}, 버전 {document['version']}\n\n"
            f"{document['text']}"
        )

    @mcp.resource("rag://index/info", mime_type="application/json")
    def index_info() -> str:
        """색인 문서 목록과 임베딩 모델 이름·차원. 질의도 같은 모델로 임베딩해야 하므로 함께 공개한다."""
        documents = [{k: v for k, v in d.items() if k != "text"} for d in store.list_documents()]
        return json.dumps(
            {"embedding_model": embedder.model, "dimension": embedder.dimension, "documents": documents},
            ensure_ascii=False,
            default=str,
        )

    return mcp


def warn_on_model_mismatch(store: Store, embedder: Embedder) -> None:
    """색인 때와 다른 임베딩 모델로 검색하면 결과가 엉뚱해지므로 시작할 때 알린다. indexer가 다시 색인한다."""
    stale = [d["doc_id"] for d in store.list_documents() if d.get("embedding_model") not in (None, embedder.model)]
    if stale:
        logger.warning("임베딩 모델이 %s와 다른 문서 %d건: %s. rag-indexer를 다시 실행하세요.",
                       embedder.model, len(stale), ", ".join(stale))


def main() -> None:
    """compose 안에서 Streamable HTTP로 실행한다."""
    from rag_mcp.embedding import embedder_from_env
    from rag_mcp.store import store_from_env

    logging.basicConfig(level=logging.INFO)
    embedder = embedder_from_env()
    store = store_from_env(embedder.dimension)
    warn_on_model_mismatch(store, embedder)
    server = build_server(store, embedder)
    server.run(transport="http", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "9102")), path="/mcp")


if __name__ == "__main__":
    main()
