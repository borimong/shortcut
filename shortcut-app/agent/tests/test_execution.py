"""실행팀 subgraph(supervisor와 실행 Agent 6개)와 수정 요청(계획 단계 분기, 실행 단계 재지시)을 검증합니다."""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.graph.builder import build_replan_graph
from app.graph.execution import STAGE_OF, build_execution_graph
from app.harness.limits import new_counter
from app.worker import TaskRunner
from tests.fakes import FakeBackendState, FakeModel, make_context

CONFIG = {"configurable": {"thread_id": "event-1"}}


def run(coro):
    return asyncio.run(coro)


def facts(**overrides):
    base = {
        "taskId": 1,
        "shootDayId": 1,
        "location": {"id": 3, "name": "파주 세트장", "indoor": True},
        "originalLocation": {"id": 1, "name": "한강 공원"},
        "start": "14:00",
        "end": "16:00",
        "originalStart": "13:00",
        "originalEnd": "15:00",
        "equipment": [{"id": 1, "name": "카메라 패키지 A"}, {"id": 4, "name": "추가 조명 패키지"}],
        "originalEquipmentIds": [1, 2, 3],
        "drone": False,
        "headcount": 12,
        "changed": ["LOCATION", "TIME", "EQUIPMENT", "COST"],
        "costKrw": 850000,
        "extraCostKrw": 550000,
        "event": "13시 이후 비",
        "unresolved": [],
    }
    return {**base, **overrides}


def exec_input(f=None, **extra):
    return {
        "facts": f or facts(),
        "prior_reports": [],
        "revise_order": None,
        "step_seq": 10,
        "loop_counter": new_counter(),
        "rounds": 0,
        "stage": 0,
        "retries": {},
        "skipped": [],
        **extra,
    }


def run_exec(ctx, data):
    return run(build_execution_graph().compile().ainvoke(data, context=ctx))


def running_agents(events):
    return [p["agent"] for t, p in events.events if t == "AGENT" and p["status"] == "running" and p["agent"] in STAGE_OF]


def test_stages_run_in_dependency_order_and_indoor_without_drone_skips_permit():
    ctx, backend, clients, events = make_context()
    result = run_exec(ctx, exec_input())
    assert result["outcome"] == "DONE"
    started = running_agents(events)
    # 같은 단계 안에서는 순서가 정해지지 않지만, 앞 단계가 모두 시작된 뒤에 다음 단계가 시작된다.
    assert [STAGE_OF[a] for a in started] == sorted(STAGE_OF[a] for a in started)
    assert set(started) == {"venue", "rental", "transport", "contact", "ledger"}
    skipped = [p["agent"] for t, p in events.events if t == "AGENT" and p["status"] == "skipped"]
    assert skipped == ["permit"]
    reports = {r["agent"]: r for r in result["exec_reports"]}
    assert reports["venue"]["artifacts"]["status"] == "CONFIRMED"
    assert reports["rental"]["artifacts"]["bookingId"] == "RB-3001"
    # 장부에는 앞 단계 예약 번호가 금액 없이 넘어가고, 금액은 서버(가짜)가 채운다.
    assert {e["ref_id"] for e in backend.ops["ledger"]} == {"R-3001", "RB-3001", "TB-3001"}
    assert all("amount" not in e for e in backend.ops["ledger"])
    # 연락 안내문에는 이동 Agent가 정한 집결 장소가 들어간다.
    assert all("목동 오피스 세트" in m["text"] for m in backend.ops["messages"])


def test_parallel_agents_publish_thoughts_and_tool_events_with_agent_names():
    ctx, _, _, events = make_context()
    run_exec(ctx, exec_input())
    thoughts = [p for t, p in events.events if t == "THOUGHT"]
    assert {p["agent"] for p in thoughts} >= {"supervisor", "venue", "rental", "contact", "ledger"}
    assert all(p["phase"] == "exec" and p["revisable"] for p in thoughts)
    tools = [p for t, p in events.events if t == "TOOL_START" and p["server"] == "ops"]
    assert {p["agent"] for p in tools} == {"venue", "rental", "transport", "contact", "ledger"}


def test_venue_failure_is_retried_once_then_handed_to_human_without_later_stages():
    ctx, backend, clients, events = make_context(FakeBackendState(venue_conflict=True))
    result = run_exec(ctx, exec_input())
    assert result["outcome"] == "NEEDS_HUMAN"
    venue_runs = [r for r in result["exec_reports"] if r["agent"] == "venue"]
    assert [r["status"] for r in venue_runs] == ["FAILED", "FAILED"]
    called = {name for name, _ in clients["ops"].calls}
    # 장소가 확정되지 않았으므로 허가, 차량, 연락, 장부는 아무것도 하지 않는다.
    assert not called & {"transport_book", "send_message", "ledger_record"}


def test_permit_denial_stops_before_contact():
    ctx, _, clients, _ = make_context(FakeBackendState(permit_denied=True))
    outdoor = facts(location={"id": 1, "name": "한강 공원", "indoor": False}, originalLocation={"id": 2, "name": "성수 스튜디오"})
    result = run_exec(ctx, exec_input(outdoor))
    assert result["outcome"] == "NEEDS_HUMAN"
    permit = [r for r in result["exec_reports"] if r["agent"] == "permit"]
    # 반려는 다시 신청해도 바뀌지 않으므로 재지시 없이 바로 사람에게 넘긴다.
    assert [r["status"] for r in permit] == ["NEEDS_HUMAN"]
    assert "send_message" not in {name for name, _ in clients["ops"].calls}


def test_exec_revision_reruns_only_the_target_and_its_dependents():
    ctx, backend, clients, events = make_context()
    first = run_exec(ctx, exec_input())
    events.events.clear()
    second = run_exec(
        ctx, exec_input(prior_reports=first["exec_reports"], revise_order={"agent": "rental", "comment": "조명은 2시 도착으로"})
    )
    assert second["outcome"] == "DONE"
    assert set(running_agents(events)) == {"rental", "transport", "contact", "ledger"}
    rental_prompt = ctx.model.prompts["# 할 일: 장비 렌탈 실행"][-1]
    assert "조명은 2시 도착으로" in rental_prompt


def initial_state():
    return {
        "task_id": 1,
        "thread_id": "event-1",
        "shoot_day_id": 1,
        "event": {"id": 1, "type": "RAIN", "detail": "13시 이후 비 80%", "instruction": "", "requested_by": "manager"},
        "extra_constraints": [],
        "failed_hashes": [],
        "violations": [],
        "loop_summaries": [],
        "info_retries": 0,
        "loop_counter": new_counter(),
    }


def compile_graph(ctx):
    return build_replan_graph(ctx.settings.limits).compile(checkpointer=InMemorySaver(), store=InMemoryStore())


def runner_for(graph, ctx):
    return TaskRunner(ctx.settings, graph, None, ctx.model, None)


def test_approved_plan_runs_execution_and_reports_it_in_the_result():
    ctx, _, _, events = make_context()
    graph = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(Command(resume={"decision": "APPROVED"}), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    final = run(scenario())
    execution = final.values["result"]["execution"]
    assert execution["status"] == "DONE"
    assert {r["agent"] for r in execution["reports"]} >= {"venue", "contact", "ledger"}
    plan_thoughts = [p for t, p in events.events if t == "THOUGHT" and p["phase"] == "plan"]
    assert {p["node"] for p in plan_thoughts} >= {"analyze_impact", "collect_constraints", "compose_plan", "self_review"}
    # 같은 노드가 여러 번 돌아도 step은 겹치지 않는다(체크포인트를 찾는 키).
    steps = [p["step"] for p in plan_thoughts]
    assert len(steps) == len(set(steps))


def test_plan_revision_forks_from_the_chosen_step_and_feeds_the_comment_to_that_node():
    ctx, backend, _, events = make_context(model=FakeModel(choose_hash="L3-E1,5-T14001600"))
    graph = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        compose = next(p for t, p in events.events if t == "THOUGHT" and p["node"] == "compose_plan")
        revise = {
            "eventId": 99,
            "phase": "plan",
            "step": compose["step"],
            "node": "compose_plan",
            "agent": "planner",
            "comment": "파주로 가 주세요",
        }
        assert await runner_for(graph, ctx)._revise(revise, CONFIG, ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    # 분기한 지점(최적안 구성)부터 다시 돌아 새 변경안이 등록되고, 요청대로 파주 후보가 올라간다.
    assert len(backend.proposals) == 2
    assert backend.proposals[1]["candidate"]["location_id"] == 3
    assert any("파주로 가 주세요" in p for p in ctx.model.prompts["# 할 일: 사용자 수정 요청에 맞는 후보 고르기"])
    # 앞 단계(영향 분석)는 다시 돌지 않는다.
    assert ctx.model.structured_calls.count("ImpactSummary") == 1


def test_exec_revision_after_done_reruns_execution_once_even_if_delivered_twice():
    ctx, backend, clients, _ = make_context()
    graph = compile_graph(ctx)
    revise = {
        "eventId": 7,
        "phase": "exec",
        "step": 30,
        "node": "venue_agent",
        "agent": "venue",
        "comment": "확정 예약 다시 확인",
    }

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(Command(resume={"decision": "APPROVED"}), CONFIG, context=ctx)
        runner = runner_for(graph, ctx)
        first = await runner._revise(revise, CONFIG, ctx)
        second = await runner._revise(revise, CONFIG, ctx)
        return first, second, await graph.aget_state(CONFIG)

    first, second, state = run(scenario())
    assert first is True and second is False
    venue_reports = [r for r in state.values["exec_reports"] if r["agent"] == "venue"]
    assert len(venue_reports) == 2
    assert state.values["revisions_done"] == [7]
    assert state.values["result"]["execution"]["status"] == "DONE"
