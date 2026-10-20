"""rag-mcp: 계약서·촬영 허가 규정·대본·제작 지침을 검색하고 원문을 Resource로 공개한다 (아키텍처 문서 7장).

- Tool은 chunk 요약(snippet)을 돌려주고, 근거 패널은 Resource doc://{docId}/{section}으로 원문을 읽는다.
- 업무 데이터는 절대 바꾸지 않는다. 모든 도구가 읽기 전용이다.

실행:  python -m rag_mcp.server        → http://0.0.0.0:9102/mcp
"""
from __future__ import annotations

import json
import os
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .retriever import Retriever, open_retriever

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
TopK = Annotated[int, Field(ge=1, le=10, description="돌려받을 최대 결과 수")]


def create_server(retriever: Retriever | None = None) -> FastMCP:
    mcp = FastMCP("rag")
    holder: dict[str, Retriever] = {}

    def r() -> Retriever:
        # 색인은 첫 호출 때 연다. 테스트에서는 retriever를 직접 넣는다.
        if "r" not in holder:
            holder["r"] = retriever or open_retriever()
        return holder["r"]

    @mcp.tool(annotations=READ_ONLY)
    def search_permit_rules(query: str, region: str | None = None, k: TopK = 3) -> list[dict]:
        """지자체 촬영 허가 규정에서 질문과 관련된 조항을 찾는다.
        region은 '서울 중구'처럼 지역 이름이며, 비우면 모든 지역에서 찾는다.
        반환: [{docId, section, title, snippet, score(0~1, 높을수록 관련)}].
        야외 장소의 허가 시간대, 허가 변경·취소 절차, 우천 시 규정을 확인할 때 쓴다."""
        store = r().store
        if region and region not in store.values("region"):
            raise ToolError(f"[NO_DOCS] '{region}' 촬영 허가 규정이 없다. 있는 지역: {', '.join(store.values('region'))}. region을 비우고 다시 호출해도 된다.")
        return r().search(query, k=k, where={"type": "permit", "region": region})

    @mcp.tool(annotations=READ_ONLY)
    def search_contract_terms(actor_id: str, query: str, k: TopK = 3) -> list[dict]:
        """배우(예: A03)의 출연 계약서에서 질문과 관련된 조항을 찾는다.
        반환: [{docId, section, title, snippet, score}].
        근로시간 한도, 휴식시간, 촬영 불가 일정, 야간 촬영 조건을 확인할 때 쓴다.
        validate_schedule 위반의 source가 가리키는 조항도 이 계약서에 있다."""
        store = r().store
        if actor_id not in store.values("actorId"):
            raise ToolError(f"[NO_DOCS] 배우 {actor_id}의 계약서가 없다. 계약서가 있는 배우: {', '.join(store.values('actorId'))}.")
        return r().search(query, k=k, where={"type": "contract", "actorId": actor_id})

    @mcp.tool(annotations=READ_ONLY)
    def search_script(scene_id: str) -> list[dict]:
        """씬 ID(예: S21)의 대본을 가져온다. 반환: [{docId, section, title, snippet}].
        씬의 낮·밤, 실내·야외 설정과 분위기를 확인해 다른 장소나 시간으로 옮겨도 되는지 판단할 때 쓴다.
        전체 대본은 doc://{docId}/{section} Resource로 읽는다."""
        hits = r().scene(scene_id)
        if not hits:
            raise ToolError(f"[NO_DOCS] 씬 {scene_id}의 대본이 없다. 대본이 있는 씬: {', '.join(r().store.values('sceneId'))}.")
        return hits

    @mcp.resource("doc://{doc_id}/{section}", mime_type="text/markdown")
    def read_section(doc_id: str, section: str) -> str:
        """문서 한 조항(또는 대본 한 씬)의 원문. 근거 패널과 위반 source가 이 주소를 쓴다."""
        c = r().section_text(doc_id, section)
        if c is None:
            secs = r().store.sections(doc_id)
            if not secs:
                raise ResourceError(f"문서 {doc_id}가 없다. 있는 문서: {', '.join(r().store.doc_ids())}")
            raise ResourceError(f"{doc_id}에 section {section}이 없다. 있는 section: {', '.join(secs)}")
        return f"# {c.title}\n## {c.sectionTitle}\n\n{c.text}"

    @mcp.resource("doc://index", mime_type="application/json")
    def doc_index() -> str:
        """색인된 문서와 section 목록, Embedding 모델 정보."""
        store = r().store
        return json.dumps(
            {
                "embeddingModel": store.meta["embeddingModel"],
                "dim": store.meta["dim"],
                "docs": [{"docId": d, "sections": store.sections(d)} for d in store.doc_ids()],
            },
            ensure_ascii=False,
        )

    return mcp


mcp = create_server()

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "9102")),
        path="/mcp",
    )
