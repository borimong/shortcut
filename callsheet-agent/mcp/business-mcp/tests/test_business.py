"""business-mcp 테스트 (계약 rc2). mock-backend를 메모리 안에서 띄워 연결한다 (네트워크 없음).

    cd mcp/business-mcp && pytest -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock-backend"))

try:
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

from fastmcp import Client
from fastmcp.exceptions import ToolError
from mock_backend.app import STATE
from mock_backend.app import app as mock_app

from business_mcp.backend import BackendClient, ctx_headers
from business_mcp.server import create_server

PM = {"id": 3, "role": "PRODUCTION_MANAGER", "projectId": "drama-ep07", "taskId": "t_test_0001"}
DOP = {"id": 7, "role": "DOP", "projectId": "drama-ep07", "taskId": "t_test_0002"}
DATE = "2026-11-12"
PREMIUM = {"location": 0.35, "equipment": 0.30, "weather": 0.10, "budget": 0.05, "time": 0.10, "distance": 0.10}
NOISE = {"kind": "EXCLUDE_LOCATION", "locationId": "L02", "reason": "성수 스튜디오 오후 공사 소음, 동시녹음 불가", "fromRole": "SOUND_LEAD"}
DESTRUCTIVE = {"commit_plan", "request_location_booking"}
WRITES = {"link_entity", "save_plan"} | DESTRUCTIVE


def make_server(transport=None):
    STATE.reset()
    be = BackendClient("http://mock", "dev-internal-token", transport=transport or httpx.ASGITransport(app=mock_app))
    return create_server(be)


def data(result):
    sc = getattr(result, "structured_content", None)
    if sc is None:
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


async def decide(plan_id: int, decision: str = "APPROVE", role: str | None = None, reason: str | None = None) -> dict:
    """승인자 응답 흉내 (실제로는 화면 → backend)."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock") as c:
        r = await c.post(f"/mock/plans/{plan_id}/decisions", json={"role": role, "decision": decision, "reason": reason})
        return r.json()


async def call(client, name, **args):
    return data(await client.call_tool(name, args))


# ---------------------------------------------------------------- 형식


def test_ctx_headers():
    with pytest.raises(ValueError, match="projectId"):
        ctx_headers({"id": 3, "role": "AD1", "taskId": "t_x"})
    assert ctx_headers(PM)["X-Project-Id"] == "drama-ep07"


@pytest.mark.anyio
async def test_tools_and_annotations():
    async with Client(make_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert len(tools) == 15
    for name, t in tools.items():
        assert t.description, name
        assert bool(t.annotations.destructive_hint) == (name in DESTRUCTIVE), name
        assert bool(t.annotations.read_only_hint) == (name not in WRITES), name


# ---------------------------------------------------------------- 온톨로지


@pytest.mark.anyio
async def test_impact_and_entity_context():
    async with Client(make_server()) as client:
        imp = await call(client, "find_impacted_entities", event_type="WEATHER", entity_type="LOCATION",
                         entity_id="L01", date=DATE, start="13:00", end="18:00", ctx=PM)
        ctx = await call(client, "get_entity_context", entity_type="ACTOR", entity_id="A04", ctx=PM)
        with pytest.raises(ToolError) as e:
            await call(client, "get_entity_context", entity_type="ACTOR", entity_id="A09", ctx=PM)
    assert [b["blockId"] for b in imp["blocks"]] == ["B2"] and imp["blocks"][0]["hasPlanSet"]
    a04 = next(a for a in imp["actors"] if a["actorId"] == "A04")
    assert a04["currentContractDocId"] == "contract-A04-v3" and a04["managerUserIds"] == [31]
    assert "permit-hangang" in imp["regulationDocIds"]
    rel = {(r["relation"], r["target"]["id"]) for r in ctx["relations"]}
    assert ("HAS_CONTRACT", "contract-A04-v3") in rel and ("MANAGED_BY", "31") in rel
    assert "A04" in str(e.value) and "[ENTITY_NOT_FOUND]" in str(e.value)


# ---------------------------------------------------------------- 재평가·재조합


@pytest.mark.anyio
async def test_evaluate_recombines_and_respects_weights():
    async with Client(make_server()) as client:
        ps = await call(client, "get_plan_set", block_id="B2", date=DATE, ctx=PM)
        base = await call(client, "evaluate_plans", block_id="B2", ctx=PM)
        prem = await call(client, "evaluate_plans", block_id="B2", weights=PREMIUM, ctx=PM)
        loop2 = await call(client, "evaluate_plans", block_id="B2", extra_constraints=[NOISE], ctx=PM)
    assert set(ps["plans"]) == {"P1", "P2", "P3"}
    assert base["originalPlans"]["P1"]["feasible"] is False                    # 1안은 13시 이후 우천
    assert base["ranked"][0]["choice"] == {"location": "P2", "equipment": "P1", "time": "P2"}
    assert base["ranked"][0]["recombined"] is True
    assert prem["ranked"][0]["choice"] == {"location": "P2", "equipment": "P2", "time": "P2"}   # 웃돈 OK → 추가 조명
    assert loop2["ranked"][0]["choice"] == {"location": "P3", "equipment": "P3", "time": "P1"}  # 소음 거절 반영
    assert all(r["choice"]["location"] != "P2" for r in loop2["ranked"])


@pytest.mark.anyio
async def test_validate_reports_hard_categories_with_sources():
    async with Client(make_server()) as client:
        plan1 = await call(client, "build_schedule", block_id="B2", choice={"location": "P1", "equipment": "P1", "time": "P1"}, ctx=PM)
        v1 = await call(client, "validate_plan", plan_hash=plan1["planHash"], ctx=PM)
        drone = await call(client, "build_schedule", block_id="B2", choice={"location": "P3", "equipment": "P1", "time": "P1"}, ctx=PM)
        v2 = await call(client, "validate_plan", plan_hash=drone["planHash"], ctx=PM)
    assert v1["valid"] is False and [v["code"] for v in v1["violations"]] == ["SCHEDULE.OUTDOOR_RAIN"]
    assert v1["violations"][0]["source"] == {"docId": "permit-hangang", "section": "3.1"}
    assert {v["code"] for v in v2["violations"]} == {"NO_FILMING_ZONE.DRONE"}
    assert set(v1["scores"]) == {"location", "equipment", "weather", "budget", "time", "distance"}


# ---------------------------------------------------------------- 다중 승인 → 거절 → 재계획 → 확정


@pytest.mark.anyio
async def test_reject_then_replan_then_commit():
    async with Client(make_server()) as client:
        best = (await call(client, "evaluate_plans", block_id="B2", ctx=PM))["ranked"][0]
        v8 = await call(client, "save_plan", plan_hash=best["planHash"], reason="13시 이후 우천 → 장소 2안 + 장비 1안 + 시간대 2안", ctx=PM)
        roles = [a["role"] for a in v8["requiredApprovers"]]
        assert v8["version"] == "v8" and "SOUND_LEAD" in roles and "PRODUCTION_PD" not in roles and v8["bookingNeeded"]

        with pytest.raises(ToolError) as e:
            await call(client, "commit_plan", plan_id=v8["planId"], data_version=v8["dataVersion"], ctx=PM)
        assert "[APPROVAL_REQUIRED]" in str(e.value) and "SOUND_LEAD" in str(e.value)

        res = await decide(v8["planId"], "REJECT", "SOUND_LEAD", "성수 스튜디오 오후 공사 소음")
        assert res["planStatus"] == "REJECTED" and res["resumeMessage"]["approval"]["result"] == "REJECTED"

        best2 = (await call(client, "evaluate_plans", block_id="B2", extra_constraints=[NOISE], ctx=PM))["ranked"][0]
        v9 = await call(client, "save_plan", plan_hash=best2["planHash"], reason="음향감독 거절 반영 → 장소 3안 + 장비 3안 + 시간대 1안", ctx=PM)
        assert {"DOP", "GRIP_CHIEF", "AD2"} <= {a["role"] for a in v9["requiredApprovers"]} and not v9["bookingNeeded"]
        await decide(v9["planId"], "APPROVE")
        with pytest.raises(ToolError) as e2:
            await call(client, "request_location_booking", plan_id=v9["planId"], location_id="L03", ctx=PM)
        assert "[BOOKING_NOT_NEEDED]" in str(e2.value)
        done = await call(client, "commit_plan", plan_id=v9["planId"], data_version=v9["dataVersion"], ctx=PM)
        again = await call(client, "commit_plan", plan_id=v9["planId"], data_version=v9["dataVersion"], ctx=PM)
    assert done == again and done["scheduleVersion"] == 9 and done["callsheetJobs"] > 0
    assert next(b for b in STATE.blocks if b["blockId"] == "B2")["locationId"] == "L03"
    assert len(STATE.outbox) == 1                                              # 두 번 호출해도 배포는 한 번


@pytest.mark.anyio
async def test_booking_after_approval_is_manual_pending():
    async with Client(make_server()) as client:
        best = (await call(client, "evaluate_plans", block_id="B2", ctx=PM))["ranked"][0]
        v8 = await call(client, "save_plan", plan_hash=best["planHash"], reason="r", ctx=PM)
        with pytest.raises(ToolError):
            await call(client, "request_location_booking", plan_id=v8["planId"], location_id="L02", ctx=PM)
        await decide(v8["planId"], "APPROVE")
        bk = await call(client, "request_location_booking", plan_id=v8["planId"], location_id="L02", ctx=PM)
    assert bk["status"] == "MANUAL_PENDING" and bk["assigneeRole"] == "PRODUCTION_MANAGER"


@pytest.mark.anyio
async def test_stale_plan_after_source_change():
    async with Client(make_server()) as client:
        best = (await call(client, "evaluate_plans", block_id="B2", ctx=PM))["ranked"][0]
        v8 = await call(client, "save_plan", plan_hash=best["planHash"], reason="r", ctx=PM)
        await decide(v8["planId"], "APPROVE")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock") as c:
            await c.post("/mock/data-version/bump")                           # 승인 대기 중 원본 변경
        with pytest.raises(ToolError) as e:
            await call(client, "commit_plan", plan_id=v8["planId"], data_version=v8["dataVersion"], ctx=PM)
    assert "[STALE_PLAN]" in str(e.value) and "evaluate_plans" in str(e.value)


@pytest.mark.anyio
async def test_gate_rejects_violating_plan_and_wrong_role():
    async with Client(make_server()) as client:
        bad = await call(client, "build_schedule", block_id="B2", choice={"location": "P1", "equipment": "P1", "time": "P1"}, ctx=PM)
        with pytest.raises(ToolError) as e1:
            await call(client, "save_plan", plan_hash=bad["planHash"], reason="r", ctx=PM)
        with pytest.raises(ToolError) as e2:
            await call(client, "save_plan", plan_hash=bad["planHash"], reason="r", ctx=DOP)
    assert "[HARD_VIOLATION]" in str(e1.value) and "OUTDOOR_RAIN" in str(e1.value)
    assert "[FORBIDDEN]" in str(e2.value)


# ---------------------------------------------------------------- 외부 서비스·장애


@pytest.mark.anyio
async def test_external_tools():
    async with Client(make_server()) as client:
        w = await call(client, "get_weather", location_id="L01", date=DATE, ctx=PM)
        r = await call(client, "get_route", from_location_id="L03", to_location_id="L02", ctx=PM)
        q = await call(client, "get_equipment_quote", package_id="PKG-LIGHT", date=DATE, ctx=PM)
        s = await call(client, "search_locations", area="성수", indoor=True, ctx=PM)
    assert next(h for h in w["hourly"] if h["hour"] == "13:00")["rainProb"] == 80
    assert (r["km"], r["minutes"]) == (41, 60)
    assert q["extraCost"] == 320_000
    assert [p["placeId"] for p in s["results"]] == ["OP-101"]


@pytest.mark.anyio
async def test_backend_down_and_bad_ctx():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    async with Client(make_server(httpx.MockTransport(refuse))) as client:
        with pytest.raises(ToolError) as e1:
            await call(client, "get_plan_set", block_id="B2", date=DATE, ctx=PM)
    async with Client(make_server()) as client:
        with pytest.raises(ToolError) as e2:
            await call(client, "get_plan_set", block_id="B2", date=DATE, ctx={"id": 3})
    assert "[RETRYABLE]" in str(e1.value)
    assert "[BAD_CONTEXT]" in str(e2.value)
