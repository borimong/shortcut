"""재계획 그래프의 분기, 반복, 승인 대기와 재개, 멈춤 조건을 검증합니다."""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.graph.builder import build_replan_graph
from app.graph.nodes import by_setting_fit, constraints_for_issues, pick_after_rejection
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


def test_impact_analysis_names_the_block_node_to_start_from():
    ctx, _, _, _ = make_context()
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    assert "블록의 노드 ID는 BLOCK:1-PM입니다" in ctx.model.impact_prompts[0]
    assert "shoot_day_id(값 1)를 함께 넘기세요" in ctx.model.impact_prompts[0]


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


def test_review_stops_when_the_score_stays_the_same_twice():
    # 미리보기에서 1회차 비 이벤트(한강 공원 12~16시 시간당 12mm)에 "배우 대기 시간을 줄여 줘"를 주자 76점이 다섯 번 반복됐다.
    # 피드백은 SCRIPT WARN 감점, 이동 거리와 추가 비용 설명 부족, 연출 확인 담당 누락이었다.
    model = FakeModel(
        review_scores=[76],
        review_actions=["REWRITE", "NEXT_CANDIDATE", "REWRITE", "NEXT_CANDIDATE", "REWRITE"],
    )
    ctx, backend, _, _ = make_context(model=model)
    backend.script_warnings = True
    state = initial_state()
    state["event"] = {
        "id": 1,
        "type": "RAIN",
        "detail": "한강 공원 12~16시 시간당 12mm",
        "changes": [{"kind": "RAIN_FORECAST", "targetId": 1, "fromHour": 12, "toHour": 16, "mm": 12}],
        "instruction": "배우 대기 시간을 줄여 줘",
        "requested_by": "manager",
    }
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(state, CONFIG, context=ctx))

    proposal = backend.proposals[0]
    review = proposal["review"]
    assert review["rounds"] == 3 and review["passed"] is False and review["stalled"] is True
    assert review["score"] == 76 and review["chosenRound"] == 1
    assert ctx.model.structured_calls.count("PlanReview") == 3
    # 모델이 SCRIPT를 PASS로 적어도 엔진 대본 경고가 있으면 승인자에게 보이도록 WARN으로 싣는다(근거는 그대로).
    script = next(c for c in proposal["checklist"] if c["constraint"] == "SCRIPT")
    assert script["status"] == "WARN" and script["evidence_ids"]
    assert not any(u.startswith("SCRIPT") for u in proposal["unresolved"])
    # 검토가 되풀이해 지적한 거리, 비용, 연출 확인 담당은 코드가 엔진 값으로 채워 승인 요청에 실린다.
    assert "목동 기준 이동 거리는 14km이고, 현재 확정안보다 150,000원이 더 듭니다." in proposal["explanation"]
    assert "연출감독, 야외 장면을 실내에서 찍는 연출 확인, 승인 시" in proposal["unresolved"]


def test_checklist_and_follow_ups_follow_the_engine():
    # 미리보기 1회차 우천 변경안(성수 스튜디오, 카메라 패키지 A, 드론, 반사판, 14:00~16:00)에서 모델이 엔진 판정에 없는
    # NO_FLY_ZONE WARN을 적고, 순서는 그대로(S12 다음 S13)이고 시각만 13시에서 14시로 늦췄는데 "바뀐 씬 순서"를 공지하라고 썼다.
    model = FakeModel(
        checklist_warn={"NO_FLY_ZONE": "드론 사용이 금지된 지역입니다."},
        unresolved_extra=["조감독, 바뀐 씬 순서로 배우 콜타임 다시 공지, 승인 즉시"],
    )
    ctx, backend, _, _ = make_context(model=model)
    backend.script_warnings = True
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    status = {c["constraint"]: c["status"] for c in proposal["checklist"]}
    no_fly = next(c for c in proposal["checklist"] if c["constraint"] == "NO_FLY_ZONE")
    # 엔진 위반이나 경고가 없는 범주는 PASS이고 근거 조각은 그대로 붙는다. WARN은 엔진 경고가 있는 SCRIPT뿐이다.
    assert no_fly["status"] == "PASS" and no_fly["evidence_ids"] and "금지된 지역" not in no_fly["note"]
    assert [c for c, v in status.items() if v == "WARN"] == ["SCRIPT"]
    assert not any("씬 순서" in u for u in proposal["unresolved"])
    assert "조감독, 바뀐 촬영 시각으로 배우 콜타임 다시 공지, 승인 즉시" in proposal["unresolved"]


def test_explanation_must_not_claim_an_unchanged_scene_order():
    from app.graph.nodes import explanation_problems
    from tests.fakes import SEONGSU

    current = {"location": {"id": 2, "name": "성수 스튜디오"}, "equipment": []}
    gear = "카메라 패키지 A, 드론, 반사판을 씁니다."
    assert explanation_problems(f"성수 스튜디오로 옮기고 씬 순서를 바꿔 14시에 시작합니다. {gear}", SEONGSU, [SEONGSU], current) == [
        "설명에 바뀌지 않은 씬 순서를 바뀌었다고 썼습니다"
    ]
    assert explanation_problems(f"성수 스튜디오로 옮기고 씬 순서는 그대로 두고 시각만 바뀝니다. {gear}", SEONGSU, [SEONGSU], current) == []


def test_josa_follows_the_final_sound():
    from app.josa import josa

    assert josa("성수 스튜디오", "은") == "성수 스튜디오는"
    assert josa("파주 세트장", "으로") == "파주 세트장으로"
    assert josa("반사판", "을") == "반사판을"
    assert josa("S18, S19", "은") == "S18, S19는"
    assert josa("v1", "으로") == "v1로"
    assert josa("v2", "이") == "v2가"
    assert josa("실내, 자연광", "으로") == "실내, 자연광으로"
    assert josa("배우 B 일정(18:30~21:00 광고와 행사)", "과") == "배우 B 일정(18:30~21:00 광고와 행사)과"


def test_explanation_missing_equipment_is_rewritten_then_completed():
    # 미리보기 변경안 설명이 장비 묶음(카메라 패키지 A, 드론, 반사판) 가운데 카메라 패키지 A만 적었다.
    ctx, backend, _, _ = make_context(model=FakeModel(drop_equipment=True))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    assert ctx.model.structured_calls.count("PlanExplanation") == 2
    assert proposal["explanation"].count("장비 묶음은 카메라 패키지 A, 드론, 반사판입니다.") == 1
    assert not any(u.startswith("설명 확인 필요") for u in proposal["unresolved"])


def test_engine_facts_are_not_added_twice():
    from app.graph.nodes import align_follow_ups, missing_cost_and_distance

    candidate = {**SEONGSU, "warnings": [{"code": "SCRIPT_EXT_INDOOR"}, {"code": "SCRIPT_EXT_INDOOR"}]}
    assert missing_cost_and_distance("목동에서 14km, 추가 비용 15만 원입니다.", candidate) == ""
    assert missing_cost_and_distance("목동에서 14 km 떨어져 있고 150,000원이 더 듭니다.", candidate) == ""
    assert missing_cost_and_distance("150,000원이 더 듭니다.", candidate) == "목동 기준 이동 거리는 14km입니다."
    # 미리보기에서 "14.0km"가 있는데도 "14km" 문장을 또 붙였다. 표기가 달라도 같은 값이면 붙이지 않는다.
    assert missing_cost_and_distance("이동 거리는 14.0km이며 추가 비용은 15만원입니다.", candidate) == ""
    assert missing_cost_and_distance("이동 거리는 14.0km입니다.", candidate) == "현재 확정안보다 150,000원이 더 듭니다."
    same_time = {"start": "14:00:00", "end": "16:00:00"}
    assert align_follow_ups(candidate, same_time, []) == ["연출감독, 야외 장면을 실내에서 찍는 연출 확인, 승인 시"]
    assert align_follow_ups(candidate, same_time, ["연출감독, 실내 촬영 연출 확인, 승인 시"]) == [
        "연출감독, 실내 촬영 연출 확인, 승인 시"
    ]
    changed = {**SEONGSU, "sceneOrderChanged": True}
    assert align_follow_ups(changed, same_time, []) == ["조감독, 바뀐 씬 순서로 배우 콜타임 다시 공지, 승인 즉시"]


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
        "설명에 제안 장비가 빠졌습니다: 카메라 패키지 A, 드론, 반사판",
    ]
    assert explanation_problems("성수 스튜디오로 옮기고 카메라 패키지 A를 씁니다.", SEONGSU, [SEONGSU], current) == [
        "설명에 제안 장비가 빠졌습니다: 드론, 반사판"
    ]


def test_reordered_candidate_carries_scene_order_to_tools_and_explanation():
    # 2회차처럼 배우 일정 때문에 엔진이 S19를 먼저 찍도록 순서를 바꾼 후보다.
    from app.graph.nodes import describe, explanation_problems, to_mcp_candidate
    from tests.fakes import SEONGSU

    reordered = {
        **SEONGSU,
        "sceneOrderChanged": True,
        "sceneOrder": [
            {"code": "S19", "start": "14:00", "end": "14:30"},
            {"code": "S18", "start": "14:30", "end": "16:00"},
        ],
    }
    assert describe(reordered).endswith("씬 순서 변경 S19 14:00~14:30 → S18 14:30~16:00")
    assert to_mcp_candidate(reordered)["scene_order"] == ["S19", "S18"]
    assert "scene_order" not in to_mcp_candidate(SEONGSU)

    current = {"location": {"id": 2, "name": "성수 스튜디오"}, "equipment": []}
    text = "성수 스튜디오 그대로 S19를 먼저 찍고 S18을 14:30에 시작합니다. 카메라 패키지 A와 드론, 반사판을 씁니다."
    assert explanation_problems(text, reordered, [reordered], current) == []
    assert explanation_problems("성수 스튜디오에서 그대로 찍습니다.", reordered, [reordered], current) == [
        "설명에 제안 장비가 빠졌습니다: 카메라 패키지 A, 드론, 반사판",
        "설명에 바뀐 씬 순서가 없습니다: S19 → S18",
    ]


def test_closest_candidate_skips_locked_set_and_prefers_fewest_violations():
    # 2회차 성수 취소와 배우 C 불참. 점수 1등 한강안은 세트 고정에 걸려 어떤 조율로도 성립하지 않는다.
    from app.graph.nodes import closest_candidate
    from tests.fakes import SEONGSU

    def blocked(name, location_id, score, codes):
        return {**SEONGSU, "hash": name, "location": {**SEONGSU["location"], "id": location_id}, "feasible": False,
                "totalScore": score, "violations": [{"code": c} for c in codes]}

    hangang = blocked("hangang", 1, 0.887, ["ACTOR_UNAVAILABLE", "SCRIPT_SETTING_LOCKED"])
    seongsu_early = blocked("seongsu-13", 2, 0.70, ["LOCATION_CANCELLED", "ACTOR_UNAVAILABLE", "LOCATION_CLOSED"])
    seongsu = blocked("seongsu-14", 2, 0.65, ["LOCATION_CANCELLED", "ACTOR_UNAVAILABLE"])
    assert closest_candidate([hangang, seongsu_early, seongsu])["hash"] == "seongsu-14"
    assert closest_candidate([hangang])["hash"] == "hangang"
    assert closest_candidate([{**SEONGSU, "feasible": True}, seongsu]) == {**SEONGSU, "feasible": True}
    assert closest_candidate([]) is None


def test_adjusted_time_candidate_is_described_outside_reviewed_options():
    # 1/2/3안 시간대가 배우 일정으로 모두 막혀 엔진이 배우 가능 시간에 맞춰 만든 시간대(안 번호 0)다.
    from app.graph.nodes import describe, to_mcp_candidate
    from tests.fakes import SEONGSU

    adjusted = {**SEONGSU, "time": {"optionNo": 0, "start": "14:30", "end": "16:30"}}
    assert "시간 14:30~16:30(조정 시간, 1/2/3안 밖)" in describe(adjusted)
    assert to_mcp_candidate(adjusted)["source"]["time"] == 0


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


def handoff_state(event, shoot_day_id):
    state = initial_state()
    state["shoot_day_id"] = shoot_day_id
    state["event"] = {"id": 1, "instruction": "", "requested_by": "pd", **event}
    return state


def run_to_end(ctx, state):
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(state, CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    return run(scenario())


def test_cancelled_studio_with_actor_schedule_is_not_solved_by_a_new_place():
    # 미리보기 2회차: 성수 대관 취소인데 모든 후보가 배우 C 일정과 성수 세트 고정에 막혀 새 장소로는 풀리지 않는다.
    blockers = ["배우 C 일정(10:30~14:30 타 작품)과 겹칩니다.",
                "S18, S19는 세트가 성수 스튜디오에만 있어 파주 세트장에서 찍을 수 없습니다."]
    ctx, backend, clients, _ = make_context(FakeBackendState(no_feasible=True, location_blockers=blockers))
    state = run_to_end(ctx, handoff_state(
        {"type": "LOCATION_CANCEL", "detail": "성수 스튜디오 대관 취소 통보",
         "changes": [{"kind": "LOCATION_UNAVAILABLE", "targetId": 2}]}, 2))

    result = state.values["result"]
    assert state.values["stop_condition"] == NO_FEASIBLE_PLAN
    assert not state.values.get("alternatives_tried")
    assert "search_locations" not in [name for name, _ in clients["business"].calls]
    assert result["suggestions"] == []
    assert result["blockers"] == blockers
    assert "배우 C 일정" in result["reason"] and "성수 스튜디오에만" in result["reason"]
    assert backend.proposals == []


def test_broken_reflector_with_actor_promotion_is_not_solved_by_a_new_place():
    # 미리보기 3회차: 반사판 고장에 배우 B 18:30~21:00 광고 일정이 모든 밤 후보와 겹친다.
    blockers = ["배우 B 일정(18:30~21:00 광고와 행사)과 겹칩니다."]
    ctx, _, clients, _ = make_context(FakeBackendState(no_feasible=True, location_blockers=blockers))
    state = run_to_end(ctx, handoff_state(
        {"type": "EQUIPMENT_FAILURE", "detail": "반사판 고장, 배우 B 저녁 광고 일정",
         "changes": [{"kind": "EQUIPMENT_UNAVAILABLE", "targetId": 3},
                     {"kind": "ACTOR_BUSY", "targetId": 2, "from": "18:30", "to": "21:00", "reasonKind": "PROMOTION"}]}, 3))

    assert "search_locations" not in [name for name, _ in clients["business"].calls]
    assert state.values["result"]["suggestions"] == []
    assert state.values["result"]["blockers"] == blockers


def test_alternatives_follow_the_scene_setting_unless_weather_blocks_outdoors():
    places = [{"id": 1, "name": "상암 호리존 스튜디오", "indoor": True, "keywords": ["실내"]},
              {"id": 5, "name": "망원 루프탑", "indoor": False, "keywords": ["야외", "도심 야경"]}]
    night_exterior = {"plan_set": {"block": {"scenes": [{"code": "S21", "intExt": "EXT", "timeOfDay": "NIGHT"}]}},
                      "event": {"type": "LOCATION_CANCEL"}, "candidates": []}
    assert [p["id"] for p in by_setting_fit(places, night_exterior)] == [5, 1]
    rain = {**night_exterior, "event": {"type": "RAIN"}}
    assert [p["id"] for p in by_setting_fit(places, rain)] == [1, 5]
    interior = {**night_exterior, "plan_set": {"block": {"scenes": [{"code": "S18", "intExt": "INT", "timeOfDay": "DAY"}]}}}
    assert [p["id"] for p in by_setting_fit(places, interior)] == [1, 5]
