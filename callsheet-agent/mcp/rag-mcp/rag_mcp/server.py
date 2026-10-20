"""rag-mcp: 규정·법규·계약 조항 원문 검색 (계약 rc2, contracts/mcp-tools.json).

- 근로기준법(주 52시간·휴게), 계약법 가이드, 촬영 허가, 촬영 금지 구역 고시, 출연 계약서 조항을 검색한다.
- 계약서는 온톨로지가 특정한 '현재 버전' docId 범위 안에서만 검색한다(엉뚱한 배우·옛 버전 근거 차단).
- 원문은 Resource doc://{docId}/{section}으로 읽는다(교안 필수). get_source는 같은 원문을 도구로도 준다.
- 업무 데이터는 바꾸지 않는다. 모든 도구가 읽기 전용이다.

실행:  python -m rag_mcp.server        → http://0.0.0.0:9102/mcp
"""
from __future__ import annotations

import json
import os
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .retriever import Retriever, open_retriever

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
TopK = Annotated[int, Field(ge=1, le=10, description="돌려받을 최대 결과 수")]
Category = Literal["LABOR_LAW", "CONTRACT_LAW", "FILMING_PERMIT", "NO_FILMING_ZONE"]


def create_server(retriever: Retriever | None = None) -> FastMCP:
    mcp = FastMCP("rag")
    holder: dict[str, Retriever] = {}

    def r() -> Retriever:
        if "r" not in holder:
            holder["r"] = retriever or open_retriever()
        return holder["r"]

    def find(doc_id: str, sec: str):
        """Chunk를 찾고, 없으면 다시 시도에 쓸 안내 문장을 돌려준다."""
        c = r().section_text(doc_id, sec)
        if c is not None:
            return c
        secs = r().store.sections(doc_id)
        if not secs:
            return f"문서 {doc_id}가 없다. 있는 문서: {', '.join(r().store.doc_ids())}"
        return f"{doc_id}에 section {sec}이 없다. 있는 section: {', '.join(secs)}"

    @mcp.tool(annotations=READ_ONLY)
    def search_regulation(query: str, category: Category | None = None, k: TopK = 3) -> list[dict]:
        """규정·법규 원문에서 질문과 관련된 조항을 찾는다.
        category: LABOR_LAW(근로기준법: 주 52시간, 휴게), CONTRACT_LAW(계약·위약 가이드), FILMING_PERMIT(촬영 허가·우천 시 규정),
        NO_FILMING_ZONE(드론 비행 금지 등 촬영 금지 구역 고시). 비우면 전체에서 찾는다.
        반환: [{docId, section, title, snippet, score(0~1)}]. 하드 제약의 근거를 확보할 때 쓰고, 근거 ID(docId+section)를 답변에 붙인다."""
        where = {"type": "regulation", "category": category}
        return r().search(query, k=k, where=where)

    @mcp.tool(annotations=READ_ONLY)
    def search_contract_clause(contract_doc_id: str, query: str, k: TopK = 3) -> list[dict]:
        """출연 계약서 한 건 안에서만 조항을 찾는다. contract_doc_id는 get_entity_context나 find_impacted_entities가 알려 준
        '현재 버전' 계약서 docId(예: contract-A04-v3)를 그대로 쓴다. 배우 이름이나 옛 버전으로 찾지 않는다.
        반환: [{docId, section, title, snippet, score}]. 야간 촬영, 1일 최대 시간, 초과 촬영, 촬영 불가 일정 조항 확인에 쓴다."""
        store = r().store
        chunks = store.filter({"docId": contract_doc_id})
        if not chunks or chunks[0].meta.get("type") != "contract":
            raise ToolError(f"[NO_DOCS] 계약서 {contract_doc_id}가 없다. 있는 계약서: {', '.join(store.doc_ids(type='contract'))}. "
                            "get_entity_context(ACTOR, 배우ID)로 현재 계약서 docId를 확인하라.")
        meta = chunks[0].meta
        if meta.get("status") == "SUPERSEDED":
            raise ToolError(f"[SUPERSEDED] {contract_doc_id}는 옛 버전이다(v{meta.get('version')}). "
                            f"현재 버전 {meta.get('supersededBy')}로 다시 검색하라.")
        return r().search(query, k=k, where={"docId": contract_doc_id})

    @mcp.tool(annotations=READ_ONLY)
    def get_source(doc_id: str, section: str) -> dict:
        """조항 하나의 원문 전체를 가져온다. 위반의 source나 검색 결과의 docId·section을 그대로 넣는다.
        반환: {docId, section, title, text}. Resource doc://{docId}/{section}과 같은 내용이다."""
        c = find(doc_id, section)
        if isinstance(c, str):
            raise ToolError(f"[NO_DOCS] {c}")
        return {"docId": c.docId, "section": c.section, "title": f"{c.title} {c.sectionTitle}", "text": c.text}

    @mcp.resource("doc://{doc_id}/{section_id}", mime_type="text/markdown")
    def read_section(doc_id: str, section_id: str) -> str:
        """문서 한 조항의 원문. 화면의 근거 패널과 위반 source가 이 주소를 쓴다."""
        c = find(doc_id, section_id)
        if isinstance(c, str):
            raise ResourceError(c)
        return f"# {c.title}\n## {c.sectionTitle}\n\n{c.text}"

    @mcp.resource("doc://index", mime_type="application/json")
    def doc_index() -> str:
        """색인된 문서·section 목록과 Embedding 모델 정보."""
        store = r().store
        docs = []
        for d in store.doc_ids():
            meta = store.filter({"docId": d})[0].meta
            docs.append({"docId": d, "type": meta.get("type"), "category": meta.get("category"),
                         "status": meta.get("status"), "sections": store.sections(d)})
        return json.dumps({"embeddingModel": store.meta["embeddingModel"], "dim": store.meta["dim"], "docs": docs}, ensure_ascii=False)

    return mcp


mcp = create_server()

if __name__ == "__main__":
    mcp.run(transport="http", host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "9102")), path="/mcp")
