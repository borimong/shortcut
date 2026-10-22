"""business-mcp 도구 계약과 오류 변환을 인메모리 MCP Client로 검증한다 (backend는 httpx.MockTransport)."""
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

from business_mcp.server import BackendClient, build_server

# shortcut-app/agent가 부르는 도구 (agent/app/graph, harness/guardrails.py 기준, 접두어 business_ 제외)
AGENT_TOOLS = {
    "get_entity_context", "find_impacted_entities", "link_entity",
    "get_plan_set", "get_availability", "get_weather", "get_disaster_alerts",
    "get_actor_schedule", "find_unplaceable_scenes",
    "search_locations", "register_alternative_locations",
    "evaluate_plans", "validate_plan", "get_proposal", "submit_proposal", "commit_plan",
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


def test_tool_names_match_agent_and_annotations_are_set():
    server = make_server(lambda request: httpx.Response(200, json={}))

    async def scenario():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in run(scenario())}
    assert set(tools) == AGENT_TOOLS
    assert all(tool.description for tool in tools.values())
    assert tools["get_plan_set"].annotations.read_only_hint is True
    assert tools["submit_proposal"].annotations.read_only_hint is False
    assert tools["register_alternative_locations"].annotations.read_only_hint is False
    assert tools["commit_plan"].annotations.destructive_hint is True


def test_evaluate_plans_sends_backend_contract_fields():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["token"] = request.headers["X-Internal-Token"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"dataVersion": 1, "feasibleCount": 0, "candidates": []})

    result = call(
        make_server(handler),
        "evaluate_plans",
        {
            "shoot_day_id": 1,
            "weights": {"budget": 0.05},
            "extra_constraints": [
                {"type": "EXCLUDE_LOCATION_TIME", "location_id": 2, "from_time": "13:00", "to_time": "18:00"}
            ],
        },
    )
    assert data(result)["dataVersion"] == 1
    assert captured["path"] == "/internal/plans/evaluate"
    assert captured["token"] == "token"
    assert captured["body"]["weights"] == {"budget": 0.05}
    assert captured["body"]["extraConstraints"][0] == {
        "type": "EXCLUDE_LOCATION_TIME", "locationId": 2, "from": "13:00", "to": "18:00", "reason": "", "source": "",
    }


def test_submit_proposal_maps_snake_case_to_camel_case():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"proposalId": 7, "status": "PENDING"})

    result = call(
        make_server(handler),
        "submit_proposal",
        {
            "task_id": 3, "event_id": 5, "shoot_day_id": 1, "loop_no": 1,
            "candidate": {"location_id": 2, "equipment_ids": [3, 1], "start": "14:00", "end": "16:00",
                          "source": {"location": 2, "equipment": 1, "time": 2}},
            "score": 0.74, "score_breakdown": {"location": 0.9}, "weights": {"location": 0.25},
            "explanation": "우천으로 실내 2안 장소로 옮긴다",
            "checklist": [{"constraint": "LAW", "status": "PASS", "evidence_ids": ["law-labor-standards#2"]}],
            "evidence": [{"id": "law-labor-standards#2", "doc_id": "law-labor-standards", "title": "근로기준법", "text": "..."}],
            "unresolved": [], "data_version": 4,
        },
    )
    assert data(result)["proposalId"] == 7
    body = captured["body"]
    assert captured["path"] == "/internal/proposals"
    assert body["candidate"] == {"locationId": 2, "equipmentIds": [1, 3], "start": "14:00", "end": "16:00",
                                 "source": {"location": 2, "equipment": 1, "time": 2}}
    assert body["checklist"][0]["evidenceIds"] == ["law-labor-standards#2"]
    assert body["evidence"][0]["docId"] == "law-labor-standards"
    assert body["dataVersion"] == 4 and body["taskId"] == 3


def test_validate_plan_sends_scene_order_only_when_given():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"valid": True, "sceneOrderChanged": True})

    server = make_server(handler)
    candidate = {"location_id": 2, "equipment_ids": [5, 1], "start": "14:00", "end": "16:00"}
    call(server, "validate_plan",
         {"shoot_day_id": 2, "candidate": {**candidate, "scene_order": ["S19", "S18"]}, "data_version": 1})
    call(server, "validate_plan", {"shoot_day_id": 2, "candidate": candidate, "data_version": 1})
    assert bodies[0]["candidate"]["sceneOrder"] == ["S19", "S18"]
    assert "sceneOrder" not in bodies[1]["candidate"]


def test_paths_for_read_tools():
    paths = []

    def handler(request):
        paths.append((request.method, request.url.path, dict(request.url.params)))
        # 실제 backend의 /impact는 객체(ImpactResponse)를 돌려주고, 재난 문자와 장소 검색만 목록을 돌려준다.
        if request.url.path == "/internal/ontology/impact":
            return httpx.Response(200, json={"nodes": [], "edges": []})
        return httpx.Response(200, json=[])

    server = make_server(handler)
    call(server, "find_impacted_entities", {"node_id": "LOCATION:1"})
    call(server, "get_disaster_alerts", {"shoot_day_id": 1})
    found = call(server, "search_locations", {"keywords": ["실내", "자연광"]})
    assert paths[0] == ("GET", "/internal/ontology/impact", {"nodeId": "LOCATION:1", "depth": "2"})
    assert paths[1][1] == "/internal/shoot-days/1/disaster-alerts"
    assert paths[2][2] == {"keywords": "실내,자연광", "maxDistanceKm": "40"}
    assert data(found) == {"locations": []}


def test_conflict_becomes_non_retryable_tool_error_with_next_step():
    def handler(request):
        return httpx.Response(409, json={"code": "VERSION_CONFLICT", "message": "데이터 버전이 다릅니다"})

    with pytest.raises(ToolError) as error:
        call(make_server(handler), "commit_plan", {"proposal_id": 3, "data_version": 1})
    text = str(error.value)
    assert "[VERSION_CONFLICT]" in text
    assert "evaluate_plans" in text
    assert text.endswith("(retryable=false)")


def test_plan_invalid_lists_violation_codes():
    def handler(request):
        return httpx.Response(422, json={"code": "PLAN_INVALID", "message": "하드 제약을 위반한 후보입니다.",
                                         "violations": [{"code": "WEATHER_RAIN"}, {"code": "NO_FLY_ZONE"}]})

    candidate = {"location_id": 1, "equipment_ids": [1], "start": "13:00", "end": "15:00"}
    with pytest.raises(ToolError) as error:
        call(make_server(handler), "validate_plan", {"shoot_day_id": 1, "candidate": candidate, "data_version": 1})
    assert "WEATHER_RAIN, NO_FLY_ZONE" in str(error.value)


def test_backend_down_and_5xx_are_retryable():
    def down(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ToolError) as error:
        call(make_server(down), "get_plan_set", {"shoot_day_id": 1})
    assert "[BACKEND_UNAVAILABLE]" in str(error.value) and "retryable=true" in str(error.value)

    def boom(request):
        return httpx.Response(500, json={"code": "INTERNAL_ERROR", "message": "서버 오류가 발생했습니다."})

    with pytest.raises(ToolError) as error:
        call(make_server(boom), "get_weather", {"shoot_day_id": 1})
    assert "[INTERNAL_ERROR]" in str(error.value) and "retryable=true" in str(error.value)


def test_block_and_shoot_day_node_ids_reach_backend():
    paths = []

    def handler(request):
        paths.append(dict(request.url.params))
        return httpx.Response(200, json={"edges": [], "nodes": []})

    server = make_server(handler)
    call(server, "find_impacted_entities", {"node_id": "BLOCK:1-PM", "depth": 3})
    call(server, "find_impacted_entities", {"node_id": "SHOOT_DAY:1", "depth": 1})
    call(server, "find_impacted_entities", {"node_id": "PLAN:2-1", "depth": 1})
    assert paths == [
        {"nodeId": "BLOCK:1-PM", "depth": "3"},
        {"nodeId": "SHOOT_DAY:1", "depth": "1"},
        {"nodeId": "PLAN:2-1", "depth": "1"},
    ]


def test_shoot_day_id_limits_impact_to_one_shoot_day():
    paths = []

    def handler(request):
        paths.append(dict(request.url.params))
        return httpx.Response(200, json={"edges": [], "nodes": []})

    call(make_server(handler), "find_impacted_entities", {"node_id": "SCENE:S12", "shoot_day_id": 1})
    assert paths == [{"nodeId": "SCENE:S12", "depth": "2", "shootDayId": "1"}]


def test_invalid_node_id_is_rejected_before_backend_call():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ToolError):
        call(make_server(handler), "get_entity_context", {"node_id": "배우A"})
    assert calls == []


def test_node_not_found_message_tells_model_the_id_format():
    def handler(request):
        return httpx.Response(404, json={"code": "NODE_NOT_FOUND", "message": "노드가 없습니다"})

    with pytest.raises(ToolError) as error:
        call(make_server(handler), "get_entity_context", {"node_id": "ACTOR:9"})
    assert "SCENE:S12" in str(error.value)


def test_register_alternative_locations_backend_contract():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"locationId": 101, "externalId": 1, "name": "일산 실내 스튜디오", "fit": 0.8}])

    result = call(make_server(handler), "register_alternative_locations",
                  {"shoot_day_id": 1, "external_location_ids": [1], "keywords": ["실내", "자연광"]})
    assert captured["path"] == "/internal/shoot-days/1/alternative-locations"
    assert captured["body"] == {"externalLocationIds": [1], "keywords": ["실내", "자연광"]}
    assert data(result)["registered"][0]["locationId"] == 101


def test_actor_schedule_and_unplaceable_scene_paths():
    paths = []

    def handler(request):
        paths.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"from": "2026-10-22", "to": "2026-10-28", "actors": []})

    server = make_server(handler)
    call(server, "get_actor_schedule", {"shoot_day_id": 2, "actor_ids": [1, 3], "from_date": "2026-10-22", "days": 7})
    call(server, "get_actor_schedule", {"shoot_day_id": 1})
    call(server, "find_unplaceable_scenes", {"shoot_day_id": 1})
    assert paths[0] == ("/internal/shoot-days/2/actor-schedule", {"days": "7", "actorIds": "1,3", "from": "2026-10-22"})
    assert paths[1] == ("/internal/shoot-days/1/actor-schedule", {"days": "14"})
    assert paths[2][0] == "/internal/shoot-days/1/unplaceable-scenes"


def test_actor_schedule_rejects_too_many_days_before_backend_call():
    server = make_server(lambda request: pytest.fail("backend를 부르면 안 된다"))
    with pytest.raises(ToolError):
        call(server, "get_actor_schedule", {"shoot_day_id": 1, "days": 60})


def test_require_setting_match_constraint_reaches_backend():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"dataVersion": 1, "weights": {}, "feasibleCount": 0, "candidates": []})

    server = make_server(handler)
    call(server, "evaluate_plans", {"shoot_day_id": 1, "extra_constraints": [
        {"type": "REQUIRE_SETTING_MATCH", "reason": "야외 장면은 야외에서", "source": "연출감독"}]})
    assert bodies[0]["extraConstraints"] == [
        {"type": "REQUIRE_SETTING_MATCH", "reason": "야외 장면은 야외에서", "source": "연출감독"}]
