"""ops-mcp 도구 계약과 오류 변환을 인메모리 MCP Client로 검증한다 (backend는 httpx.MockTransport)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

try:
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

from ops_mcp.server import BackendClient, build_server

READ_TOOLS = {
    "venue_check",
    "rental_quote",
    "permit_check_requirement",
    "permit_status",
    "transport_quote",
    "contacts_for_change",
    "get_replies",
    "ledger_budget_status",
}
WRITE_TOOLS = {
    "venue_hold",
    "venue_confirm",
    "venue_cancel",
    "rental_book",
    "rental_cancel",
    "permit_apply",
    "transport_book",
    "transport_cancel",
    "send_message",
    "ledger_record",
}


def make_server(handler):
    return build_server(BackendClient("http://backend.test", "token", transport=httpx.MockTransport(handler)))


def run(coro):
    return asyncio.run(coro)


def data(result):
    if getattr(result, "data", None) is not None:
        return result.data
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def call(server, name, args):
    async def scenario():
        async with Client(server) as client:
            return await client.call_tool(name, args)

    return run(scenario())


def recorder():
    """요청을 (method, path, params, body)로 모으고 빈 객체로 답하는 가짜 backend."""
    seen = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, dict(request.url.params), body))
        assert request.headers["X-Internal-Token"] == "token"
        return httpx.Response(200, json={"ok": True})

    return seen, make_server(handler)


def test_tool_names_and_annotations():
    server = make_server(lambda request: httpx.Response(200, json={}))

    async def scenario():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in run(scenario())}
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    assert len(tools) == 18
    assert all(tool.description for tool in tools.values())
    assert all(tools[name].annotations.read_only_hint is True for name in READ_TOOLS)
    assert all(tools[name].annotations.read_only_hint is False for name in WRITE_TOOLS)
    assert not any(tool.annotations.destructive_hint for tool in tools.values())


def test_venue_tools():
    seen, server = recorder()
    call(server, "venue_check", {"shoot_day_id": 1, "location_id": 2, "start": "14:00", "end": "16:00"})
    call(server, "venue_hold", {"shoot_day_id": 1, "task_id": 9, "location_id": 2, "start": "14:00", "end": "16:00"})
    call(server, "venue_confirm", {"reservation_id": "R-3001"})
    call(server, "venue_cancel", {"reservation_id": "R-2031", "reason": "장소 변경"})
    assert seen[0][:3] == (
        "GET",
        "/internal/ops/venues/2/availability",
        {"shootDayId": "1", "start": "14:00", "end": "16:00"},
    )
    assert seen[1][1] == "/internal/ops/venues/holds"
    assert seen[1][3] == {"shootDayId": 1, "taskId": 9, "locationId": 2, "start": "14:00", "end": "16:00"}
    assert seen[2][:2] == ("POST", "/internal/ops/venues/reservations/R-3001/confirm")
    assert seen[3][1] == "/internal/ops/venues/reservations/R-2031/cancel"
    assert seen[3][3] == {"reason": "장소 변경"}


def test_rental_tools():
    seen, server = recorder()
    call(server, "rental_quote", {"shoot_day_id": 1, "equipment_ids": [1, 4], "start": "14:00", "end": "16:00"})
    call(server, "rental_book", {"shoot_day_id": 1, "task_id": 9, "equipment_ids": [1, 4], "start": "14:00", "end": "16:00"})
    call(server, "rental_cancel", {"booking_id": "RB-1001"})
    assert seen[0][:2] == ("POST", "/internal/ops/rentals/quote")
    assert seen[0][3] == {"shootDayId": 1, "equipmentIds": [1, 4], "start": "14:00", "end": "16:00"}
    assert seen[1][1] == "/internal/ops/rentals/bookings"
    assert seen[1][3]["taskId"] == 9 and seen[1][3]["equipmentIds"] == [1, 4]
    assert seen[2][:2] == ("POST", "/internal/ops/rentals/bookings/RB-1001/cancel")


def test_permit_tools():
    seen, server = recorder()
    args = {"shoot_day_id": 1, "location_id": 1, "start": "13:00", "end": "15:00"}
    call(server, "permit_check_requirement", {**args, "drone": True})
    call(server, "permit_apply", {**args, "task_id": 9, "kind": "DRONE"})
    call(server, "permit_status", {"permit_id": "PM-1001"})
    assert seen[0][:2] == ("GET", "/internal/ops/permits/requirement")
    assert seen[0][2] == {"shootDayId": "1", "locationId": "1", "start": "13:00", "end": "15:00", "drone": "true"}
    assert seen[1][:2] == ("POST", "/internal/ops/permits")
    assert seen[1][3] == {"shootDayId": 1, "taskId": 9, "locationId": 1, "start": "13:00", "end": "15:00", "kind": "DRONE"}
    assert seen[2][:2] == ("GET", "/internal/ops/permits/PM-1001")


def test_permit_kind_is_validated():
    seen, server = recorder()
    with pytest.raises(ToolError):
        call(
            server,
            "permit_apply",
            {"shoot_day_id": 1, "task_id": 9, "location_id": 1, "start": "13:00", "end": "15:00", "kind": "PARKING"},
        )
    assert seen == []


def test_transport_tools():
    seen, server = recorder()
    call(
        server,
        "transport_quote",
        {"shoot_day_id": 1, "dest_location_id": 2, "start": "14:00", "headcount": 18, "equipment_ids": [1, 2, 3]},
    )
    call(
        server,
        "transport_book",
        {
            "shoot_day_id": 1,
            "task_id": 9,
            "dest_location_id": 2,
            "vehicle": "BUS_25",
            "count": 1,
            "depart_at": "13:02",
            "pickup": "목동 오피스 세트",
            "headcount": 18,
        },
    )
    call(server, "transport_cancel", {"booking_id": "TB-1001"})
    assert seen[0][:2] == ("POST", "/internal/ops/transport/quote")
    assert seen[0][3] == {"shootDayId": 1, "destLocationId": 2, "start": "14:00", "headcount": 18, "equipmentIds": [1, 2, 3]}
    assert seen[1][3] == {
        "shootDayId": 1,
        "taskId": 9,
        "destLocationId": 2,
        "vehicle": "BUS_25",
        "count": 1,
        "departAt": "13:02",
        "pickup": "목동 오피스 세트",
        "headcount": 18,
    }
    assert seen[2][:2] == ("POST", "/internal/ops/transport/bookings/TB-1001/cancel")


def test_contact_tools():
    seen, server = recorder()
    call(server, "contacts_for_change", {"shoot_day_id": 1, "changed": ["LOCATION", "TIME"]})
    call(
        server,
        "send_message",
        {
            "shoot_day_id": 1,
            "task_id": 9,
            "messages": [
                {"recipient_id": "ACTOR:1", "text": "13:30 목동 오피스 세트 집결"},
                {"recipient_id": "USER:ad1", "text": "성수 스튜디오 R-3001 확정"},
            ],
        },
    )
    call(server, "get_replies", {"task_id": 9})
    assert seen[0][:3] == ("GET", "/internal/ops/contacts", {"shootDayId": "1", "changed": "LOCATION,TIME"})
    assert seen[1][1] == "/internal/ops/messages"
    assert seen[1][3]["messages"] == [
        {"recipientId": "ACTOR:1", "text": "13:30 목동 오피스 세트 집결"},
        {"recipientId": "USER:ad1", "text": "성수 스튜디오 R-3001 확정"},
    ]
    assert seen[2][:3] == ("GET", "/internal/ops/messages/replies", {"taskId": "9"})


def test_send_message_passes_round_only_when_given():
    seen, server = recorder()
    message = {"recipient_id": "ACTOR:1", "text": "13:30 집결"}
    call(server, "send_message", {"shoot_day_id": 1, "task_id": 9, "messages": [message], "round": 2})
    call(server, "send_message", {"shoot_day_id": 1, "task_id": 9, "messages": [message]})
    # 라운드가 있으면 백엔드가 작업, 라운드, 받는 사람으로 중복을 가린다. 없으면 예전 요청 그대로다.
    assert seen[0][3]["round"] == 2
    assert "round" not in seen[1][3]


def test_send_message_rejects_unknown_recipient_format():
    seen, server = recorder()
    with pytest.raises(ToolError):
        call(server, "send_message", {"shoot_day_id": 1, "task_id": 9, "messages": [{"recipient_id": "배우A", "text": "x"}]})
    assert seen == []


def test_ledger_tools_send_no_amount():
    seen, server = recorder()
    call(
        server,
        "ledger_record",
        {
            "shoot_day_id": 1,
            "task_id": 9,
            "entries": [
                {"account": "VENUE", "memo": "우천으로 성수 스튜디오 대관", "ref_type": "RESERVATION", "ref_id": "R-3001"},
                {"account": "CANCEL_FEE", "memo": "이전 렌탈 취소", "ref_type": "RENTAL", "ref_id": "RB-1001"},
            ],
        },
    )
    call(server, "ledger_budget_status", {"shoot_day_id": 1})
    assert seen[0][:2] == ("POST", "/internal/ops/ledger")
    assert seen[0][3]["entries"][0] == {
        "account": "VENUE",
        "memo": "우천으로 성수 스튜디오 대관",
        "refType": "RESERVATION",
        "refId": "R-3001",
    }
    assert all("amount" not in str(entry).lower() for entry in seen[0][3]["entries"])
    assert seen[1][:3] == ("GET", "/internal/ops/ledger/budget", {"shootDayId": "1"})


def test_backend_error_becomes_tool_message():
    def handler(request):
        return httpx.Response(409, json={"code": "VENUE_CONFLICT", "message": "같은 시간대에 다른 예약이 있습니다"})

    with pytest.raises(ToolError) as info:
        call(
            make_server(handler),
            "venue_hold",
            {"shoot_day_id": 1, "task_id": 9, "location_id": 2, "start": "14:00", "end": "16:00"},
        )
    text = str(info.value)
    assert text.startswith("[VENUE_CONFLICT] 같은 시간대에 다른 예약이 있습니다.")
    assert "실패로 보고" in text
    assert text.endswith("(retryable=false)")


def test_backend_down_is_retryable():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(ToolError) as info:
        call(make_server(handler), "get_replies", {"task_id": 9})
    assert str(info.value).startswith("[BACKEND_UNAVAILABLE]")
    assert str(info.value).endswith("(retryable=true)")
