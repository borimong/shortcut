"""HTTP 연결 점검: mock-backend, business-mcp, rag-mcp를 띄운 뒤 시연 시나리오 1을 도구로 한 바퀴 돈다.
E(Agent)가 붙기 전에 D가 "도구가 HTTP로 제대로 동작한다"를 확인하는 용도다.

    python scripts/smoke_http.py
    BUSINESS_MCP_URL=http://localhost:9101/mcp RAG_MCP_URL=http://localhost:9102/mcp BACKEND_URL=http://localhost:8080 python scripts/smoke_http.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

try:
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

from fastmcp import Client
from fastmcp.exceptions import ToolError

BUSINESS = os.environ.get("BUSINESS_MCP_URL", "http://localhost:9101/mcp")
RAG = os.environ.get("RAG_MCP_URL", "http://localhost:9102/mcp")
BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8080")
CTX = {"id": 3, "role": "AD", "productionId": 1, "taskId": "t_smoke_0001"}

FIXED = {
    "baseScheduleId": 12, "dateFrom": "2026-11-12", "dateTo": "2026-11-14",
    "slots": [
        {"date": "2026-11-12", "sceneId": "S22", "locationId": "L03", "start": "10:00", "end": "13:00", "equipmentIds": ["E01", "E03"]},
        {"date": "2026-11-12", "sceneId": "S23", "locationId": "L01", "start": "15:00", "end": "18:00", "equipmentIds": ["E01", "E03"]},
        {"date": "2026-11-13", "sceneId": "S21", "locationId": "L02", "start": "09:00", "end": "13:00", "equipmentIds": ["E01", "E02"]},
        {"date": "2026-11-13", "sceneId": "S24", "locationId": "L02", "start": "18:00", "end": "20:00", "equipmentIds": ["E01", "E04"]},
        {"date": "2026-11-14", "sceneId": "S25", "locationId": "L01", "start": "09:00", "end": "12:00", "equipmentIds": ["E01", "E02"]},
        {"date": "2026-11-14", "sceneId": "S26", "locationId": "L04", "start": "14:00", "end": "16:30", "equipmentIds": ["E01", "E04"]},
    ],
}


def data(result):
    sc = getattr(result, "structured_content", None)
    if sc is None:
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


def step(n: int, text: str) -> None:
    print(f"\n[{n}] {text}")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BACKEND) as be:
        (await be.post("/mock/reset")).raise_for_status()

    async with Client(BUSINESS) as biz, Client(RAG) as rag:
        step(1, "도구 목록")
        print("  business:", ", ".join(t.name for t in await biz.list_tools()))
        print("  rag     :", ", ".join(t.name for t in await rag.list_tools()))

        step(2, "11/12 남산 날씨, 영향받는 씬")
        w = data(await biz.call_tool("get_weather_forecast", {"location_id": "L02", "date": "2026-11-12", "ctx": CTX}))
        scenes = data(await biz.call_tool("get_scenes_by_location", {"location_id": "L02", "ctx": CTX}))
        print(f"  강수 {w['rainProb']}% → 영향 씬: {[s['sceneId'] for s in scenes]}")

        step(3, "근거 검색")
        rule = data(await rag.call_tool("search_contract_terms", {"actor_id": "A03", "query": "하루 촬영 시간 한도", "k": 1}))[0]
        text = (await rag.read_resource(f"doc://{rule['docId']}/{rule['section']}"))[0].text
        print(f"  {rule['docId']} {rule['section']}: {text.splitlines()[-1][:60]}…")

        step(4, "검증 → 수정안 재검증")
        fixed = data(await biz.call_tool("validate_schedule", {"draft": FIXED, "ctx": CTX}))
        print(f"  수정안 valid={fixed['valid']}, changedScenes={fixed['changedScenes']}, softScore={fixed['softScore']}")

        step(5, "초안 저장 → 승인 없이 확정 시도")
        draft_id = data(await biz.call_tool("save_schedule_draft", {"draft": FIXED, "reason": "11/12 남산 비 예보", "ctx": CTX}))["draftId"]
        try:
            await biz.call_tool("confirm_schedule", {"draft_id": draft_id, "ctx": CTX})
            print("  !! 승인 없이 확정됨 (오류)")
            return 1
        except ToolError as e:
            print(f"  막힘: {str(e)[:70]}…")

        step(6, "감독 승인(mock) → 확정 → 허가 취소 → 콜시트 발송")
        async with httpx.AsyncClient(base_url=BACKEND) as be:
            (await be.post(f"/mock/tasks/{CTX['taskId']}/approve", json={"decision": "APPROVE"})).raise_for_status()
        sid = data(await biz.call_tool("confirm_schedule", {"draft_id": draft_id, "ctx": CTX}))["scheduleId"]
        await biz.call_tool("update_permit_status", {"permit_id": 301, "status": "CANCELLED", "ctx": CTX})
        sent = data(await biz.call_tool("send_callsheets", {"schedule_id": sid, "recipient_ids": [11, 13, 15, 21], "ctx": CTX}))
        print(f"  scheduleId={sid}, 발송 대기 {sent['queued']}건")

    print("\nOK: 시나리오 1 완료")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
