"""contracts/examples를 mock-backend의 실제 응답으로 다시 만든다.
엔진 규칙이나 mock 데이터가 바뀌면 이 스크립트를 돌리고 check_contracts.py로 확인한다.

    python contracts/tools/gen_examples.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp" / "mock-backend"))

try:
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

from mock_backend.app import STATE, app  # noqa: E402

OUT = ROOT / "contracts" / "examples"
H = {"X-Internal-Token": "dev-internal-token", "X-User-Id": "3", "X-User-Role": "PRODUCTION_MANAGER",
     "X-Project-Id": "drama-ep07", "X-Task-Id": "t_20261112_0001"}
INDEX: list[dict] = []


def save(name: str, schema: str, body) -> None:
    (OUT / name).write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INDEX.append({"file": name, "schema": schema})


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    STATE.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock", headers=H) as c:
        async def get(path, **params):
            return (await c.get(path, params=params)).json()

        async def post(path, body=None, **kw):
            return (await c.post(path, json=body, **kw)).json()

        save("entity-context-A04.json", "domain.schema.json#/$defs/EntityContext", await get("/internal/ontology/entities/ACTOR/A04"))
        imp_req = {"eventType": "WEATHER", "entityType": "LOCATION", "entityId": "L01", "date": "2026-11-12", "start": "13:00", "end": "18:00"}
        save("impact-request.json", "domain.schema.json#/$defs/ImpactRequest", imp_req)
        save("impact-result.json", "domain.schema.json#/$defs/ImpactResult", await post("/internal/ontology/impact", imp_req))
        save("plan-set-B2.json", "plan.schema.json#/$defs/PlanSet", await get("/internal/plan-sets/B2", date="2026-11-12"))
        save("availability-A04.json", "domain.schema.json#/$defs/Availability", await get("/internal/availability", entityType="ACTOR", entityId="A04", date="2026-11-12"))
        save("weather-L01.json", "domain.schema.json#/$defs/Weather", await get("/internal/external/weather", locationId="L01", date="2026-11-12"))
        save("route-L03-L02.json", "domain.schema.json#/$defs/Route", await get("/internal/external/route", **{"from": "L03", "to": "L02"}))
        save("equipment-quote.json", "domain.schema.json#/$defs/EquipmentQuote", await get("/internal/external/equipment-quote", packageId="PKG-LIGHT", date="2026-11-12"))
        save("location-search.json", "domain.schema.json#/$defs/LocationSearchResult", await get("/internal/external/locations", area="성수"))

        ev = await post("/internal/plans/evaluate", {"blockId": "B2"})
        save("evaluation-loop1.json", "plan.schema.json#/$defs/EvaluationResult", ev)
        noise = {"kind": "EXCLUDE_LOCATION", "locationId": "L02", "reason": "성수 스튜디오 오후 공사 소음, 동시녹음 불가", "fromRole": "SOUND_LEAD"}
        save("extra-constraint.json", "plan.schema.json#/$defs/ExtraConstraint", noise)
        save("evaluate-request-loop2.json", "domain.schema.json#/$defs/EvaluateRequest", {"blockId": "B2", "extraConstraints": [noise]})
        bad = await post("/internal/plans/build", {"blockId": "B2", "choice": {"location": "P1", "equipment": "P1", "time": "P1"}})
        save("candidate-plan1.json", "plan.schema.json#/$defs/PlanCandidate", bad)
        save("validation-invalid.json", "plan.schema.json#/$defs/ValidationResult", await post("/internal/plans/validate", {"planHash": bad["planHash"]}))
        best = ev["ranked"][0]
        valid = await post("/internal/plans/validate", {"planHash": best["planHash"]})
        save("validation-valid.json", "plan.schema.json#/$defs/ValidationResult", valid)
        saved = (await c.post("/internal/plans", json={"planHash": best["planHash"], "reason": "13시 이후 우천으로 1안 불가 → 장소 2안 + 장비 1안 + 시간대 2안"})).json()
        save("saved-plan-v8.json", "plan.schema.json#/$defs/SavedPlan", saved)
        save("error-approval-required.json", "common.schema.json#/$defs/Error",
             await post(f"/internal/plans/{saved['planId']}/commit", {"dataVersion": saved["dataVersion"]}))
        dec = await post(f"/mock/plans/{saved['planId']}/decisions", {"role": "SOUND_LEAD", "decision": "REJECT", "reason": noise["reason"]})
        ev2 = await post("/internal/plans/evaluate", {"blockId": "B2", "extraConstraints": [noise]})
        save("evaluation-loop2.json", "plan.schema.json#/$defs/EvaluationResult", ev2)
        saved2 = (await c.post("/internal/plans", json={"planHash": ev2["ranked"][0]["planHash"], "reason": "음향감독 거절 반영 → 장소 3안 + 장비 3안 + 시간대 1안"})).json()
        await post(f"/mock/plans/{saved2['planId']}/decisions", {"decision": "APPROVE"})
        done = await post(f"/internal/plans/{saved2['planId']}/commit", {"dataVersion": saved2["dataVersion"]}, headers={"Idempotency-Key": "t_20261112_0001-commit_plan-802"})
        save("commit-result.json", "plan.schema.json#/$defs/CommitResult", done)
        save("error-stale.json", "common.schema.json#/$defs/Error", await post(f"/internal/plans/{saved['planId']}/commit", {"dataVersion": 7}))

    STATE.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock", headers=H) as c:
        ev = (await c.post("/internal/plans/evaluate", json={"blockId": "B2"})).json()
        s = (await c.post("/internal/plans", json={"planHash": ev["ranked"][0]["planHash"], "reason": "r"})).json()
        await c.post(f"/mock/plans/{s['planId']}/decisions", json={"decision": "APPROVE"})
        save("booking.json", "plan.schema.json#/$defs/Booking", (await c.post("/internal/bookings", json={"planId": s["planId"], "locationId": "L02"})).json())

    # ---------------------------------------------------------------- 큐·이벤트·화면 (위 응답으로 조립)
    ctx = {"id": 3, "role": "PRODUCTION_MANAGER", "projectId": "drama-ep07"}
    change = {"eventType": "WEATHER", "entityType": "LOCATION", "entityId": "L01", "date": "2026-11-12", "start": "13:00", "end": "18:00",
              "message": "13시 이후 한강 우천 예보. 오늘 오후 야외 촬영 재계획 필요", "directorInstruction": None}
    save("create-task-request.json", "api.schema.json#/$defs/CreateTaskRequest", change)
    save("mcp-ctx.json", "common.schema.json#/$defs/McpCtx", {**ctx, "taskId": "t_20261112_0001"})
    save("queue-start.json", "task.schema.json#/$defs/QueueMessage",
         {"type": "START", "taskId": "t_20261112_0001", "threadId": "t_20261112_0001", "user": ctx, "input": change, "attempt": 1})
    save("queue-resume-rejected.json", "task.schema.json#/$defs/QueueMessage",
         {"type": "RESUME", "taskId": "t_20261112_0001", "threadId": "t_20261112_0001", "user": ctx, "planId": saved["planId"],
          "approval": dec["resumeMessage"]["approval"], "attempt": 1})
    src = [{"docId": "permit-hangang", "section": "3.1", "title": "한강공원 촬영 허가 운영 기준 (가상) 3.1 기상 악화 시 촬영",
            "snippet": "강수 확률이 60% 이상인 시간대에는 공원 이용객 안전과 장비 보호를 위해 야외 촬영을 하지 않는다."}]
    events = [
        ("event-tool-start.json", {"event": "TOOL_START", "data": {"node": "analyze_impact", "tool": "business_find_impacted_entities", "label": "우천 영향 블록 찾는 중"}}),
        ("event-evaluation.json", {"event": "EVALUATION", "data": {"loop": 1, "feasibleCount": ev["feasibleCount"], "bestChoice": ev["ranked"][0]["choice"], "bestTotal": ev["ranked"][0]["total"]}}),
        ("event-approval-required.json", {"event": "APPROVAL_REQUIRED", "data": {
            "planId": saved["planId"], "version": saved["version"],
            "summary": "13시 이후 우천으로 1안(한강 야외) 불가 → 장소 2안(성수 스튜디오) + 장비 1안(기존 렌탈) + 시간대 2안(14~16시) 재조합. 추가 비용 0원",
            "choice": ev["ranked"][0]["choice"], "changes": [
                {"element": "location", "from": "L01", "to": "L02"}, {"element": "time", "from": "13:00-15:00", "to": "14:00-16:00"},
                {"element": "route", "from": "79km", "to": "82km"}],
            "total": saved["total"], "scores": valid["scores"], "extraCost": 0, "requiredApprovers": saved["requiredApprovers"],
            "sources": src, "bookingNeeded": saved["bookingNeeded"]}}),
        ("event-approval-updated.json", {"event": "APPROVAL_UPDATED", "data": {"planId": saved["planId"], "role": "SOUND_LEAD", "status": "REJECTED",
                                                                             "reason": noise["reason"], "completed": 5, "total": len(saved["requiredApprovers"])}}),
        ("event-plan-stale.json", {"event": "PLAN_STALE", "data": {"planId": saved["planId"], "currentDataVersion": 8}}),
        ("event-done.json", {"event": "DONE", "data": {"answer": f"변경안 {saved2['version']}을 확정하고 콜시트 {done['callsheetJobs']}건을 배포 대기열에 넣었습니다.", "sources": src, "scheduleVersion": done["scheduleVersion"]}}),
        ("event-escalated.json", {"event": "ESCALATED", "data": {"reason": "LOOP_LIMIT", "handoffRole": "AD1", "unresolved": [], "alternatives": []}}),
        ("event-failed.json", {"event": "FAILED", "data": {"reason": "LLM API 503이 재시도 2회와 대체 모델에서도 계속됨", "traceUrl": None}}),
    ]
    for name, body in events:
        save(name, "task.schema.json#/$defs/TaskEvent", body)
    stored = [{**events[0][1], "taskId": "t_20261112_0001", "seq": 3, "ts": "2026-11-12T10:03:12+09:00"},
              {**events[1][1], "taskId": "t_20261112_0001", "seq": 4, "ts": "2026-11-12T10:03:20+09:00"}]
    save("task-events-page.json", "api.schema.json#/$defs/TaskEventsPage", {"events": stored, "nextAfter": 4, "done": False})
    save("approval-decision-reject.json", "api.schema.json#/$defs/ApprovalDecisionRequest", {"decision": "REJECT", "reason": noise["reason"]})
    board = [dict(a) for a in saved["requiredApprovers"]]
    for a in board:
        if a["role"] in ("DIRECTOR", "AD1", "DOP", "GAFFER", "PRODUCTION_MANAGER"):
            a.update(status="APPROVED", decidedAt="2026-11-12T10:42:00+09:00")
        if a["role"] == "SOUND_LEAD":
            a.update(status="REJECTED", reason=noise["reason"], decidedAt="2026-11-12T10:47:00+09:00")
    save("approval-board.json", "api.schema.json#/$defs/ApprovalBoard",
         {"planId": saved["planId"], "version": saved["version"], "status": "REJECTED", "completed": 5, "total": len(board), "approvals": board,
          "replanning": {"loop": 2, "maxLoop": 3, "constraint": "성수 스튜디오 제외 (동시녹음팀장: 오후 공사 소음)"}})
    save("notification-list.json", "api.schema.json#/$defs/NotificationList", {"unread": 3, "nextAfter": 12, "items": [
        {"id": 12, "kind": "APPROVAL_RESULT", "title": "동시녹음팀장이 변경안 v8을 거절했습니다", "createdAt": "2026-11-12T10:47:00+09:00", "read": False, "link": f"/plans/{saved['planId']}"},
        {"id": 11, "kind": "APPROVAL_REQUEST", "title": "변경안 v8 승인이 필요합니다", "createdAt": "2026-11-12T10:04:00+09:00", "read": False, "link": f"/plans/{saved['planId']}/approvals"},
        {"id": 10, "kind": "CHANGE_NOTICE", "title": "13시 이후 우천 예보로 오늘 계획이 바뀝니다", "createdAt": "2026-11-12T09:58:00+09:00", "read": False, "link": "/projects/drama-ep07/today"}]})

    (OUT / "index.json").write_text(json.dumps(INDEX, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"examples {len(INDEX)}개 생성 → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
