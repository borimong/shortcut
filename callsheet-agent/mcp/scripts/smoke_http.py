"""HTTP 연결 점검: mock-backend, business-mcp, rag-mcp를 띄운 뒤 v2 시연 시나리오를 도구로 한 바퀴 돈다.
Agent가 할 순서를 사람이 대신 따라가 보는 스크립트다. E(Agent) 개발 때 기대 동작의 기준으로도 쓴다.

    python scripts/smoke_http.py
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
CTX = {"id": 3, "role": "PRODUCTION_MANAGER", "projectId": "drama-ep07", "taskId": "t_smoke_0001"}
DATE = "2026-11-12"


def data(result):
    sc = getattr(result, "structured_content", None)
    if sc is None:
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


def label(choice: dict) -> str:
    names = {"location": "장소", "equipment": "장비", "time": "시간대"}
    return " + ".join(f"{names[k]} {v[1]}안" for k, v in choice.items())


async def main() -> int:
    async with httpx.AsyncClient(base_url=BACKEND) as be:
        (await be.post("/mock/reset")).raise_for_status()

        async with Client(BUSINESS) as biz, Client(RAG) as rag:
            async def b(name, **kw):
                return data(await biz.call_tool(name, {**kw, "ctx": CTX}))

            print("[1] 변경 감지: 13시 이후 한강 우천 예보 → 영향 분석 (온톨로지)")
            imp = await b("find_impacted_entities", event_type="WEATHER", entity_type="LOCATION", entity_id="L01", date=DATE, start="13:00", end="18:00")
            a04 = next(a for a in imp["actors"] if a["actorId"] == "A04")
            print(f"    영향 블록 {[x['blockId'] for x in imp['blocks']]}, 배우 {[a['actorId'] for a in imp['actors']]}, A04 현재 계약서 {a04['currentContractDocId']}")

            print("[2] 제약 수집: 규정과 '현재 버전' 계약서 근거 (RAG)")
            rain = data(await rag.call_tool("search_regulation", {"query": "강수 확률 높은 시간대 야외 촬영", "category": "FILMING_PERMIT", "k": 1}))[0]
            night = data(await rag.call_tool("search_contract_clause", {"contract_doc_id": a04["currentContractDocId"], "query": "야간 촬영", "k": 1}))[0]
            print(f"    {rain['docId']} {rain['section']}, {night['docId']} {night['section']}")

            print("[3] 1/2/3안 재평가 + 요소 재조합 (backend 엔진)")
            ev = await b("evaluate_plans", block_id="B2")
            best = ev["ranked"][0]
            print(f"    27개 중 가능 {ev['feasibleCount']}개, 원래 1안 가능? {ev['originalPlans']['P1']['feasible']}")
            print(f"    최적안: {label(best['choice'])} (총점 {best['total']}, 추가 비용 {best['extraCost']:,}원)")

            print("[4] 하드 제약 검증 → 변경안 저장 → 다중 승인 요청")
            v = await b("validate_plan", plan_hash=best["planHash"])
            v8 = await b("save_plan", plan_hash=best["planHash"], reason=f"13시 이후 우천으로 1안 불가 → {label(best['choice'])}")
            print(f"    valid={v['valid']} → {v8['version']}, 필수 승인자 {len(v8['requiredApprovers'])}명")

            print("[5] 음향감독 거절 → 거절 사유를 새 제약으로 재계획 (루프 2)")
            r = (await be.post(f"/mock/plans/{v8['planId']}/decisions", json={"role": "SOUND_LEAD", "decision": "REJECT", "reason": "성수 스튜디오 오후 공사 소음, 동시녹음 불가"})).json()
            noise = {"kind": "EXCLUDE_LOCATION", "locationId": "L02", "reason": r["resumeMessage"]["approval"]["rejections"][0]["reason"], "fromRole": "SOUND_LEAD"}
            ev2 = await b("evaluate_plans", block_id="B2", extra_constraints=[noise])
            best2 = ev2["ranked"][0]
            v9 = await b("save_plan", plan_hash=best2["planHash"], reason=f"음향감독 거절 반영 → {label(best2['choice'])}")
            print(f"    v8 {r['planStatus']} → {v9['version']}: {label(best2['choice'])}")

            print("[6] 승인 전 확정 시도 → 막힘")
            try:
                await b("commit_plan", plan_id=v9["planId"], data_version=v9["dataVersion"])
                print("    !! 승인 없이 확정됨 (오류)")
                return 1
            except ToolError as e:
                print(f"    {str(e)[:60]}…")

            print("[7] 전원 승인 → 확정 → 콜시트 배포 대기열")
            (await be.post(f"/mock/plans/{v9['planId']}/decisions", json={"decision": "APPROVE"})).raise_for_status()
            done = await b("commit_plan", plan_id=v9["planId"], data_version=v9["dataVersion"])
            await b("link_entity", from_type="BLOCK", from_id="B2", relation="SHOT_AT", to_type="LOCATION", to_id="L03", attrs={"planVersion": v9["version"]})
            print(f"    확정 계획 v{done['scheduleVersion']}, 콜시트 작업 {done['callsheetJobs']}건")

    print("\nOK: v2 시나리오 완료")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
