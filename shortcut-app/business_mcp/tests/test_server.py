"""business-mcp 도구 계약과 오류 변환을 인메모리 MCP Client로 검증합니다."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from business_mcp.server import BackendClient, build_server


def make_server(handler):
    backend = BackendClient("http://backend.test", "token", transport=httpx.MockTransport(handler))
    return build_server(backend)


def run(coro):
    return asyncio.run(coro)


def test_tools_have_descriptions_and_change_tools_are_marked():
    server = make_server(lambda request: httpx.Response(200, json={}))

    async def scenario():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in run(scenario())}
    assert {
        "get_plan_set",
        "evaluate_plans",
        "submit_proposal",
        "commit_plan",
        "link_entity",
        "register_alternative_locations",
    } <= set(tools)
    assert all(tool.description for tool in tools.values())
    assert tools["get_plan_set"].annotations.read_only_hint is True
    assert tools["submit_proposal"].annotations.read_only_hint is False
    assert tools["commit_plan"].annotations.destructive_hint is True


def test_evaluate_plans_sends_backend_contract_fields():
    captured = {}

    def handler(request: httpx.Request):
        captured["path"] = request.url.path
        captured["token"] = request.headers["X-Internal-Token"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"dataVersion": 1, "feasibleCount": 0, "candidates": []})

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool(
                "evaluate_plans",
                {
                    "shoot_day_id": 1,
                    "weights": {"budget": 0.05},
                    "extra_constraints": [
                        {"type": "EXCLUDE_LOCATION_TIME", "location_id": 2, "from_time": "13:00", "to_time": "18:00"}
                    ],
                },
            )

    result = run(scenario())
    assert result.data["dataVersion"] == 1
    assert captured["path"] == "/internal/plans/evaluate"
    assert captured["token"] == "token"
    assert captured["body"]["extraConstraints"][0] == {
        "type": "EXCLUDE_LOCATION_TIME",
        "locationId": 2,
        "from": "13:00",
        "to": "18:00",
        "reason": "",
        "source": "",
    }


def test_conflict_becomes_non_retryable_tool_error():
    def handler(request):
        return httpx.Response(409, json={"code": "VERSION_CONFLICT", "message": "데이터 버전이 다릅니다"})

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("commit_plan", {"proposal_id": 3, "data_version": 1})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "[VERSION_CONFLICT]" in str(error.value)
    assert "retryable=false" in str(error.value)


def test_backend_down_becomes_retryable_tool_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("get_plan_set", {"shoot_day_id": 1})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "[BACKEND_UNAVAILABLE]" in str(error.value)
    assert "retryable=true" in str(error.value)


def test_invalid_node_id_is_rejected_before_backend_call():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("get_entity_context", {"node_id": "배우A"})

    with pytest.raises(ToolError):
        run(scenario())
    assert calls == []


def test_node_not_found_message_tells_model_the_id_format():
    def handler(request):
        return httpx.Response(404, json={"code": "NODE_NOT_FOUND", "message": "노드가 없습니다"})

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("get_entity_context", {"node_id": "ACTOR:9"})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "SCENE:S12" in str(error.value)


def test_register_alternative_locations_is_a_write_tool_with_backend_contract():
    captured = {}

    def handler(request: httpx.Request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"locationId": 101, "externalId": 1, "name": "일산 실내 스튜디오", "fit": 0.8}])

    server = make_server(handler)

    async def scenario():
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}
            result = await client.call_tool(
                "register_alternative_locations",
                {"shoot_day_id": 1, "external_location_ids": [1], "keywords": ["실내", "자연광"]},
            )
            return tools["register_alternative_locations"], result.data

    tool, data = run(scenario())
    assert tool.annotations.read_only_hint is False
    assert captured["path"] == "/internal/shoot-days/1/alternative-locations"
    assert captured["body"] == {"externalLocationIds": [1], "keywords": ["실내", "자연광"]}
    assert data["registered"][0]["locationId"] == 101
