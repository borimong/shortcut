"""business-mcp 테스트. backend 대신 mock-backend를 메모리 안에서 띄워 연결한다 (네트워크 없음).

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

AD = {"id": 3, "role": "AD", "productionId": 1, "taskId": "t_test_0001"}
STAFF = {"id": 21, "role": "STAFF", "productionId": 1, "taskId": "t_test_0002"}

RAIN_FIXED_DRAFT = {
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

DESTRUCTIVE = {"confirm_schedule", "update_permit_status", "send_callsheets"}


def make_server(transport=None):
    STATE.reset()
    backend = BackendClient("http://mock", "dev-internal-token", transport=transport or httpx.ASGITransport(app=mock_app))
    return create_server(backend)


def data(result):
    """도구 결과의 structured content. list 반환은 {"result": [...]}로 감싸져 온다."""
    sc = getattr(result, "structured_content", None)
    if sc is None:  # 구조화 결과가 없으면 텍스트(JSON)를 읽는다
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


def base_draft():
    from mock_backend import fixtures as fx
    return {"baseScheduleId": 12, "dateFrom": "2026-11-12", "dateTo": "2026-11-14", "slots": [dict(s) for s in fx.BASE_SLOTS]}


# ---------------------------------------------------------------- 단위


def test_ctx_headers_requires_all_keys():
    with pytest.raises(ValueError, match="taskId"):
        ctx_headers({"id": 1, "role": "AD", "productionId": 1})
    assert ctx_headers(AD)["X-User-Role"] == "AD"


# ---------------------------------------------------------------- 도구 목록


@pytest.mark.anyio
async def test_tools_and_annotations():
    async with Client(make_server()) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert len(tools) == 11
    for name, tool in tools.items():
        assert tool.description, f"{name}에 docstring이 없다"
        destructive = bool(tool.annotations and tool.annotations.destructive_hint)
        assert destructive == (name in DESTRUCTIVE), name


# ---------------------------------------------------------------- 조회


@pytest.mark.anyio
async def test_get_scene_and_not_found_hint():
    async with Client(make_server()) as client:
        scene = data(await client.call_tool("get_scene", {"scene_id": "S21", "ctx": AD}))
        assert scene["locationId"] == "L02" and scene["indoor"] is False

        with pytest.raises(ToolError) as e:
            await client.call_tool("get_scene", {"scene_id": "S29", "ctx": AD})
    msg = str(e.value)
    assert "[SCENE_NOT_FOUND]" in msg and "S26" in msg and "다시 호출" in msg


@pytest.mark.anyio
async def test_schedule_weather_availability():
    async with Client(make_server()) as client:
        days = data(await client.call_tool("get_shooting_schedule", {"date_from": "2026-11-12", "date_to": "2026-11-14", "ctx": AD}))
        weather = data(await client.call_tool("get_weather_forecast", {"location_id": "L02", "date": "2026-11-12", "ctx": AD}))
        avail = data(await client.call_tool("get_actor_availability", {"actor_id": "A03", "date_from": "2026-11-13", "date_to": "2026-11-13", "ctx": AD}))
    assert [d["date"] for d in days] == ["2026-11-12", "2026-11-13", "2026-11-14"]
    assert weather["rainProb"] == 80
    assert avail[0]["available"] == [{"start": "07:00", "end": "14:00"}, {"start": "18:00", "end": "23:00"}]


# ---------------------------------------------------------------- 검증


@pytest.mark.anyio
async def test_validate_finds_rain_and_actor_conflict():
    async with Client(make_server()) as client:
        result = data(await client.call_tool("validate_schedule", {"draft": base_draft(), "ctx": AD}))
    types = {(v["type"], v["target"].get("sceneId")) for v in result["violations"]}
    assert result["valid"] is False
    assert ("OUTDOOR_RAIN", "S21") in types and ("OUTDOOR_RAIN", "S24") in types
    assert ("ACTOR_UNAVAILABLE", "S23") in types        # A03 11/13 14~18 불가
    assert all("hint" in v for v in result["violations"])


@pytest.mark.anyio
async def test_validate_fixed_draft_is_valid():
    async with Client(make_server()) as client:
        result = data(await client.call_tool("validate_schedule", {"draft": RAIN_FIXED_DRAFT, "ctx": AD}))
    assert result["valid"] is True, result["violations"]
    assert result["changedScenes"] == 4


@pytest.mark.anyio
async def test_bad_draft_format_is_rejected_before_backend():
    bad = {**RAIN_FIXED_DRAFT, "dateFrom": "11/12"}
    async with Client(make_server()) as client:
        with pytest.raises(ToolError):
            await client.call_tool("validate_schedule", {"draft": bad, "ctx": AD})


# ---------------------------------------------------------------- 변경 + 승인


@pytest.mark.anyio
async def test_change_flow_requires_approval_and_is_idempotent():
    async with Client(make_server()) as client:
        draft_id = data(await client.call_tool("save_schedule_draft", {"draft": RAIN_FIXED_DRAFT, "reason": "11/12 남산 비 예보", "ctx": AD}))["draftId"]

        with pytest.raises(ToolError) as e:
            await client.call_tool("confirm_schedule", {"draft_id": draft_id, "ctx": AD})
        assert "[APPROVAL_REQUIRED]" in str(e.value)

        STATE.approvals[AD["taskId"]] = "APPROVE"   # 실제로는 backend가 /approval 요청으로 기록한다

        schedule_id = data(await client.call_tool("confirm_schedule", {"draft_id": draft_id, "ctx": AD}))["scheduleId"]
        permit = data(await client.call_tool("update_permit_status", {"permit_id": 301, "status": "CANCELLED", "ctx": AD}))
        sent1 = data(await client.call_tool("send_callsheets", {"schedule_id": schedule_id, "recipient_ids": [11, 13, 15, 21], "ctx": AD}))
        sent2 = data(await client.call_tool("send_callsheets", {"schedule_id": schedule_id, "recipient_ids": [11, 13, 15, 21], "ctx": AD}))

    assert permit["status"] == "CANCELLED"
    assert sent1 == sent2 == {"queued": 4, "recipients": [11, 13, 15, 21]}
    assert len(STATE.deliveries) == 4              # 두 번 호출해도 한 번만 발송


@pytest.mark.anyio
async def test_confirm_refuses_hard_violation():
    async with Client(make_server()) as client:
        draft_id = data(await client.call_tool("save_schedule_draft", {"draft": base_draft(), "reason": "test", "ctx": AD}))["draftId"]
        STATE.approvals[AD["taskId"]] = "APPROVE"
        with pytest.raises(ToolError) as e:
            await client.call_tool("confirm_schedule", {"draft_id": draft_id, "ctx": AD})
    assert "[HARD_VIOLATION]" in str(e.value) and "validate_schedule" in str(e.value)


@pytest.mark.anyio
async def test_staff_cannot_change_schedule():
    async with Client(make_server()) as client:
        with pytest.raises(ToolError) as e:
            await client.call_tool("save_schedule_draft", {"draft": RAIN_FIXED_DRAFT, "reason": "x", "ctx": STAFF})
    assert "[FORBIDDEN]" in str(e.value)


# ---------------------------------------------------------------- 장애


@pytest.mark.anyio
async def test_backend_down_is_retryable():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    async with Client(make_server(httpx.MockTransport(refuse))) as client:
        with pytest.raises(ToolError) as e:
            await client.call_tool("get_scene", {"scene_id": "S21", "ctx": AD})
    assert "[RETRYABLE]" in str(e.value)


@pytest.mark.anyio
async def test_missing_ctx_is_reported():
    async with Client(make_server()) as client:
        with pytest.raises(ToolError) as e:
            await client.call_tool("get_scene", {"scene_id": "S21", "ctx": {"id": 3}})
    assert "[BAD_CONTEXT]" in str(e.value)
