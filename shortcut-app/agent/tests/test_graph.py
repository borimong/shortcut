"""재계획 그래프의 분기, 반복, 승인 대기와 재개, 멈춤 조건을 검증합니다."""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.graph.builder import build_replan_graph
from app.graph.nodes import constraints_for_issues, pick_after_rejection
from app.graph.qa import build_qa_graph
from app.harness.limits import LOOP_LIMIT, NO_FEASIBLE_PLAN, new_counter
from tests.fakes import PAJU, SEONGSU, SEONGSU_MORNING, FakeBackendState, FakeModel, make_context

CONFIG = {"configurable": {"thread_id": "event-1"}}


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
    store = InMemoryStore()
    return build_replan_graph(ctx.settings.limits).compile(checkpointer=InMemorySaver(), store=store), store


def run(coro):
    return asyncio.run(coro)


def test_first_loop_stops_at_approval_and_commits_after_all_approve():
    ctx, backend, clients, events = make_context()
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        waiting = await graph.aget_state(CONFIG)
        assert waiting.next == ("await_approval",)
        assert backend.commits == []
        # backend는 마지막 이벤트로 작업 상태를 정하므로 멈추기 직전 마지막 이벤트가 승인 요청이어야 한다.
        assert events.types()[-1] == "APPROVAL_REQUIRED"
        await graph.ainvoke(Command(resume={"decision": "APPROVED"}), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    final = run(scenario())
    assert final.next == ()
    assert final.values["callsheet_version_no"] == 2
    assert backend.proposals[0]["candidate"]["location_id"] == 2
    assert backend.commits == [{"proposal_id": 10, "data_version": 1}]
    assert "APPROVAL_REQUIRED" in events.types()
    nodes = [p["node"] for t, p in events.events if t == "NODE" and p["phase"] == "end"]
    assert nodes[:6] == [
        "detect_change",
        "analyze_impact",
        "collect_constraints",
        "reevaluate_plans",
        "compose_plan",
        "validation_gate",
    ]
    assert nodes[-2:] == ["commit_plan", "publish"]


def test_rejection_becomes_constraint_and_next_loop_proposes_one_new_plan():
    ctx, backend, _, _ = make_context()
    graph, store = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(
            Command(resume={"decision": "REJECTED", "role": "SOUND", "reason": "성수 스튜디오 오후 공사 소음, 동시녹음 불가"}),
            CONFIG,
            context=ctx,
        )
        return await graph.aget_state(CONFIG), await store.asearch(("shortcut", "rejections"))

    state, memories = run(scenario())
    assert state.next == ("await_approval",)
    assert len(backend.proposals) == 2
    assert backend.proposals[1]["candidate"]["location_id"] == 3
    assert state.values["extra_constraints"][0]["type"] == "EXCLUDE_LOCATION_TIME"
    assert state.values["extra_constraints"][0]["source"] == "REJECTION:SOUND"
    assert state.values["loop_counter"]["loops"] == 2
    assert backend.evaluate_calls[-1]["extra_constraints"][0]["location_id"] == 2
    assert memories and memories[0].value["role"] == "SOUND"


def test_gate_violation_skips_to_next_candidate_in_same_loop():
    backend = FakeBackendState(validate_violations=["LOCATION_CLOSED"])
    ctx, backend, _, events = make_context(backend)
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    assert state.values["violations"][0]["codes"] == ["LOCATION_CLOSED"]
    assert backend.proposals[0]["candidate"]["location_id"] == 3
    assert state.values["loop_counter"]["loops"] == 1


def test_no_feasible_plan_suggests_alternatives_and_reports_to_human():
    ctx, backend, _, _ = make_context(FakeBackendState(no_feasible=True))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ()
    assert state.values["stop_condition"] == NO_FEASIBLE_PLAN
    assert state.values["alternatives_tried"] is True
    assert state.values["result"]["suggestions"][0]["name"] == "일산 실내 스튜디오"
    assert backend.proposals == []


def test_loop_limit_stops_after_rejection():
    ctx, backend, _, _ = make_context(max_loops=1)
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(Command(resume={"decision": "REJECTED", "role": "SOUND", "reason": "소음"}), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.values["stop_condition"] == LOOP_LIMIT
    assert len(backend.proposals) == 1


def test_version_conflict_on_commit_goes_back_to_reevaluation():
    ctx, backend, _, _ = make_context(FakeBackendState(commit_conflicts=1))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(Command(resume={"decision": "APPROVED"}), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    assert len(backend.proposals) == 2
    assert backend.commits == []


def test_pass_without_evidence_is_downgraded_to_warning():
    ctx, backend, _, _ = make_context(model=FakeModel(cite_evidence=False))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    run(scenario())
    checklist = backend.proposals[0]["checklist"]
    assert all(item["status"] == "WARN" for item in checklist)
    assert any("근거 조항 확인 필요" in u for u in backend.proposals[0]["unresolved"])


def test_cited_evidence_is_checked_against_original_resource():
    ctx, backend, _, _ = make_context()
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    evidence_ids = {e["id"] for e in backend.proposals[0]["evidence"]}
    assert "law-labor-standards#2" in evidence_ids
    assert "contract-actor-a-v3#3" in evidence_ids


def test_director_instruction_adjusts_weights_within_bounds():
    ctx, backend, _, _ = make_context()
    graph, _ = compile_graph(ctx)
    state = initial_state()
    state["event"]["instruction"] = "웃돈을 줘도 좋은 데로"
    run(graph.ainvoke(state, CONFIG, context=ctx))
    weights = backend.evaluate_calls[0]["weights"]
    assert abs(sum(weights.values()) - 1) < 0.01
    assert weights["budget"] >= 0.04
    assert weights["location"] == max(weights.values())


def test_qa_graph_answers_with_streamed_tokens():
    ctx, _, clients, events = make_context()
    graph = build_qa_graph().compile(checkpointer=InMemorySaver())
    values = run(
        graph.ainvoke(
            {"task_id": "t", "question": "왜 실내로 바꿨나요?", "proposal_id": 10, "loop_counter": new_counter()},
            {"configurable": {"thread_id": "ask-1"}},
            context=ctx,
        )
    )
    assert "safety-disaster-weather#2" in values["answer"]
    assert "safety-disaster-weather#2" in values["evidence"]
    assert events.types().count("TOKEN") > 3
    assert ("get_proposal", {"proposal_id": 10}) in clients["business"].calls


def test_registration_conflict_reevaluates_instead_of_failing():
    ctx, backend, _, _ = make_context(FakeBackendState(submit_conflicts=1))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    assert len(backend.proposals) == 1
    assert backend.proposals[0]["candidate"]["location_id"] == 3
    assert len(backend.evaluate_calls) == 2


def test_location_rejection_searches_the_fourth_plan_before_the_remaining_options():
    ctx, backend, _, events = make_context()
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(
            Command(resume={"decision": "REJECTED", "role": "SOUND", "reason": "오후 공사 소음", "issues": ["LOCATION"]}),
            CONFIG,
            context=ctx,
        )
        await graph.ainvoke(
            Command(
                resume={"decision": "REJECTED", "role": "DIRECTOR", "reason": "장면 의도와 맞지 않음", "issues": ["LOCATION"]}
            ),
            CONFIG,
            context=ctx,
        )
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    # 성수가 장소 문제로 거절되자 남은 파주(0.6)보다 먼저 대체 장소를 찾아, 점수가 더 높은 일산(0.66)을 올린다.
    # 일산이 다시 거절되면 이미 찾아봤으므로 검색 없이 파주로 간다.
    assert [p["candidate"]["location_id"] for p in backend.proposals] == [2, 101, 3]
    assert backend.proposals[1]["candidate"]["source"]["location"] == 4
    assert backend.registered == [1]
    assert state.values["loop_counter"]["loops"] == 3
    assert state.values["last_rejection"]["issues"] == ["LOCATION"]
    nodes = [p["node"] for t, p in events.events if t == "NODE" and p["phase"] == "end"]
    assert "suggest_alternatives" in nodes


def _plan(location_id, start, end, equipment_ids, score):
    return {
        "hash": f"L{location_id}-{start}",
        "feasible": True,
        "location": {"id": location_id},
        "time": {"start": start, "end": end},
        "equipment": {"items": [{"id": i} for i in equipment_ids]},
        "totalScore": score,
    }


def test_rejection_keeps_elements_that_were_not_the_problem():
    rejected = {"issues": ["TIME"], "location_id": 2, "start": "14:00", "end": "16:00", "equipment_ids": [1, 4]}
    other_place = _plan(3, "13:00", "15:00", [1, 4], 0.9)
    same_place = _plan(2, "15:00", "17:00", [1, 4], 0.7)
    assert pick_after_rejection([other_place, same_place], rejected) is same_place
    assert pick_after_rejection([other_place, same_place], None) is other_place


def test_constraints_outside_chosen_issues_are_dropped():
    candidate = {"location": {"id": 2}, "time": {"start": "14:00", "end": "16:00"}, "extraCost": 150000}
    proposed = [
        {"type": "EXCLUDE_LOCATION", "location_id": 2},
        {"type": "EXCLUDE_TIME", "from_time": "14:00", "to_time": "16:00"},
    ]
    kept, dropped = constraints_for_issues(proposed, ["LOCATION"], candidate)
    assert kept == [{"type": "EXCLUDE_LOCATION", "location_id": 2}]
    assert dropped == [{"type": "EXCLUDE_TIME", "from_time": "14:00", "to_time": "16:00"}]


def test_missing_issue_gets_a_default_constraint_from_the_rejected_plan():
    candidate = {"location": {"id": 2}, "time": {"start": "14:00", "end": "16:00"}, "extraCost": 150000}
    kept, _ = constraints_for_issues([{"type": "EXCLUDE_LOCATION", "location_id": 2}], ["LOCATION", "COST"], candidate)
    assert {"type": "MAX_EXTRA_COST", "amount": 149999} in kept
    assert constraints_for_issues([], ["OTHER"], candidate) == ([], [])


def _validate_calls(clients):
    return sum(1 for name, _ in clients["business"].calls if name == "validate_plan")


def test_review_below_threshold_rewrites_until_it_passes():
    ctx, backend, clients, _ = make_context(model=FakeModel(review_scores=[60, 70, 85], review_actions=["REWRITE"]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    review = backend.proposals[0]["review"]
    assert review["passed"] is True and review["score"] == 85 and review["rounds"] == 3
    assert [h["score"] for h in review["history"]] == [60, 70, 85]
    # 설명만 고친 회차는 같은 후보라 검증 게이트를 다시 부르지 않는다.
    assert _validate_calls(clients) == 1
    assert ctx.model.structured_calls.count("PlanExplanation") == 3


def test_review_stops_after_five_rounds_and_submits_the_best_round():
    ctx, backend, _, _ = make_context(model=FakeModel(review_scores=[50, 65, 40, 55, 30], review_actions=["REWRITE"]))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    review = backend.proposals[0]["review"]
    assert review["passed"] is False and review["rounds"] == 5
    assert review["score"] == 65 and review["chosenRound"] == 2


def test_review_can_switch_to_the_next_candidate():
    ctx, backend, clients, _ = make_context(model=FakeModel(review_scores=[50, 90], review_actions=["NEXT_CANDIDATE", "REWRITE"]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    assert backend.proposals[0]["candidate"]["location_id"] == 3
    assert backend.proposals[0]["review"]["history"][0]["action"] == "NEXT_CANDIDATE"
    assert _validate_calls(clients) == 2


def test_review_switches_method_when_the_score_does_not_improve():
    ctx, backend, _, _ = make_context(model=FakeModel(review_scores=[60, 60, 85], review_actions=["REWRITE"]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    history = backend.proposals[0]["review"]["history"]
    assert [h["action"] for h in history[:2]] == ["REWRITE", "NEXT_CANDIDATE"]
    assert backend.proposals[0]["candidate"]["location_id"] == 3


def test_explanation_naming_another_candidate_is_rewritten_once():
    ctx, backend, _, _ = make_context(model=FakeModel(explanation_extras=["짐벌 세트도 챙깁니다."]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    assert ctx.model.structured_calls.count("PlanExplanation") == 2
    assert "짐벌 세트" not in proposal["explanation"]
    assert not any(u.startswith("설명 확인 필요") for u in proposal["unresolved"])


def test_explanation_still_wrong_after_rewrite_goes_to_unresolved():
    ctx, backend, _, _ = make_context(model=FakeModel(explanation_extras=["짐벌 세트도 챙깁니다."] * 2))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    assert any("짐벌 세트" in u for u in backend.proposals[0]["unresolved"] if u.startswith("설명 확인 필요"))


def test_explanation_may_name_the_original_plan():
    # 원래 확정안(한강 공원, 카메라 패키지 A)과 선택한 안의 이름만 있으면 문제가 없다.
    from app.graph.nodes import explanation_problems
    from tests.fakes import HANGANG, PAJU, SEONGSU

    current = {"location": {"id": 1, "name": "한강 공원"}, "equipment": [{"id": 1}]}
    text = "한강 공원에서 성수 스튜디오로 옮기고 카메라 패키지 A와 드론, 반사판을 씁니다."
    assert explanation_problems(text, SEONGSU, [SEONGSU, PAJU, HANGANG], current) == []
    assert explanation_problems("파주 세트장으로 옮깁니다.", SEONGSU, [SEONGSU, PAJU, HANGANG], current) == [
        "설명에 선택한 장소가 없습니다: 성수 스튜디오",
        "설명에 선택하지 않은 장소나 장비가 있습니다: 파주 세트장",
    ]


def _reject_location(graph, ctx):
    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(
            Command(
                resume={"decision": "REJECTED", "role": "SOUND", "reason": "성수 스튜디오 공사 소음", "issues": ["LOCATION"]}
            ),
            CONFIG,
            context=ctx,
        )
        return await graph.aget_state(CONFIG)

    return run(scenario())


def test_rejected_location_is_not_proposed_again_even_with_a_narrow_constraint():
    ctx, backend, _, _ = make_context(FakeBackendState(narrow_constraints=True, no_alternatives=True))
    graph, _ = compile_graph(ctx)
    state = _reject_location(graph, ctx)
    # 장소가 문제였으니 시간이 다른 성수 오전 후보(0.75)보다 점수가 낮아도 파주를 올린다.
    assert backend.proposals[1]["candidate"]["location_id"] == 3
    assert state.values["rejected_plans"][0]["location_id"] == 2


def test_filtered_repeats_are_excluded_and_reevaluated_when_nothing_is_left():
    ctx, backend, _, _ = make_context(FakeBackendState(narrow_constraints=True, top_k=1, no_alternatives=True))
    graph, _ = compile_graph(ctx)
    _reject_location(graph, ctx)
    # 엔진이 성수 오전 후보 하나만 돌려줬으므로, 그 후보를 빼고 다시 평가해 파주를 받는다.
    assert backend.proposals[1]["candidate"]["location_id"] == 3
    assert SEONGSU_MORNING["hash"] in backend.evaluate_calls[-1]["exclude_hashes"]


def test_repeats_follow_only_the_chosen_issues():
    from app.graph.nodes import repeats_rejection

    rejected = [
        {"issues": ["TIME"], "location_id": 2, "equipment_ids": [1, 2, 3], "start": "14:00", "end": "16:00", "extra_cost": 150000}
    ]
    # 시간만 문제였으면 같은 장소의 다른 시간은 다시 올릴 수 있다.
    assert repeats_rejection(SEONGSU_MORNING, rejected) is False
    assert repeats_rejection(SEONGSU, rejected) is True
    assert repeats_rejection(PAJU, [{**rejected[0], "issues": ["COST"], "extra_cost": 150000}]) is True


def test_location_rejection_without_found_places_continues_with_remaining_options():
    ctx, backend, _, _ = make_context(FakeBackendState(no_alternatives=True))
    graph, _ = compile_graph(ctx)
    state = _reject_location(graph, ctx)
    # 일찍 찾은 대체 장소가 없어도 사람에게 넘기지 않고 남은 파주로 이어 간다.
    assert [p["candidate"]["location_id"] for p in backend.proposals] == [2, 3]
    assert state.values.get("stop_condition") is None


def test_rejection_of_other_elements_does_not_search_new_places():
    ctx, backend, _, events = make_context()
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        await graph.ainvoke(
            Command(resume={"decision": "REJECTED", "role": "DOP", "reason": "드론 배터리 불량", "issues": ["EQUIPMENT"]}),
            CONFIG,
            context=ctx,
        )

    run(scenario())
    nodes = [p["node"] for t, p in events.events if t == "NODE" and p["phase"] == "end"]
    assert "suggest_alternatives" not in nodes
