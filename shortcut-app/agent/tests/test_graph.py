"""재계획 그래프의 분기, 반복, 승인 대기와 재개, 멈춤 조건을 검증합니다."""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.graph.builder import build_replan_graph
from app.graph.nodes import (
    NO_DISASTER_ALERT_ID,
    applies_to_places,
    candidate_places,
    constraints_for_issues,
    counts_as_evidence,
    data_evidence,
    evidence_score,
    fact_problems,
    mentions,
    pick_after_rejection,
    quoted,
)
from app.graph.qa import build_qa_graph
from app.graph.schemas import ConstraintFinding, ConstraintSet, PlanExplanation, QuotedCheck
from app.graph.state import HARD_CONSTRAINTS
from app.harness.limits import LOOP_LIMIT, NO_FEASIBLE_PLAN, new_counter
from tests.fakes import PAJU, SEONGSU, SEONGSU_MORNING, THOUGHT, FakeBackendState, FakeModel, _task_line, make_context

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
    # 확정 뒤 실행팀이 돌고 공지로 끝난다.
    assert nodes[-2:] == ["execute", "publish"]
    assert nodes[nodes.index("commit_plan") + 1] == "supervisor"


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
    checklist = {item["constraint"]: item for item in backend.proposals[0]["checklist"]}
    # 재난 문자는 조회 결과(0건)가 근거라 모델이 인용하지 않아도 통과다.
    assert checklist.pop("DISASTER")["status"] == "PASS"
    assert all(item["status"] == "WARN" for item in checklist.values())
    assert any("근거 조항 확인 필요" in u for u in backend.proposals[0]["unresolved"])


def test_no_disaster_alert_is_evidence_for_the_disaster_category():
    ctx, backend, _, _ = make_context()
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    disaster = next(item for item in proposal["checklist"] if item["constraint"] == "DISASTER")
    assert disaster["status"] == "PASS" and NO_DISASTER_ALERT_ID in disaster["evidence_ids"]
    # 조회 결과는 rag 원문 대조 없이 근거 패널에 실린다.
    assert any(e["id"] == NO_DISASTER_ALERT_ID and e["doc_type"] == "DATA" for e in proposal["evidence"])


def test_disaster_alert_data_counts_only_when_no_alert_was_issued():
    assert NO_DISASTER_ALERT_ID in data_evidence({"disaster_alerts": {"alerts": []}})
    assert data_evidence({"disaster_alerts": {"alerts": [{"type": "HEAVY_RAIN"}]}}) == {}
    assert data_evidence({}) == {}
    fact = data_evidence({"disaster_alerts": {"alerts": []}})[NO_DISASTER_ALERT_ID]
    assert counts_as_evidence("DISASTER", fact) and not counts_as_evidence("WEATHER", fact)


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


# 가짜 검토 모델이 아니오로 답할 점검 질문 묶음이다. 가짜 설명에는 숫자가 한 종류뿐이고 비용 이유가 없어 모두 맞혀도 86점이다.
BAD = ("change", "reason")  # 73점
MID = ("reason",)  # 79점


def test_review_below_threshold_rewrites_until_it_passes():
    ctx, backend, clients, _ = make_context(model=FakeModel(review_misses=[BAD, MID, ()]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    review = backend.proposals[0]["review"]
    assert review["passed"] is True and review["score"] == 86 and review["rounds"] == 3
    assert [h["score"] for h in review["history"]] == [73, 79, 86]
    # 설명만 고친 회차는 같은 후보라 검증 게이트를 다시 부르지 않는다.
    assert _validate_calls(clients) == 1
    assert ctx.model.structured_calls.count("PlanExplanation") == 3


def test_review_stops_after_five_rounds_and_submits_the_best_round():
    ctx, backend, _, _ = make_context(model=FakeModel(review_misses=[BAD, MID, BAD, BAD, BAD]))
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return await graph.aget_state(CONFIG)

    state = run(scenario())
    assert state.next == ("await_approval",)
    review = backend.proposals[0]["review"]
    assert review["passed"] is False and review["rounds"] == 5
    assert review["score"] == 79 and review["chosenRound"] == 2


def test_blocking_reason_stops_a_plan_even_at_the_pass_score():
    # 숫자 두 종류와 비용 이유를 넣으면 변경 이벤트에 대응하지 않아도 80점이 되지만 통과시키지 않는다.
    extra = "촬영은 14:00~16:00, 추가 비용 150,000원은 대관료입니다."
    ctx, backend, _, _ = make_context(model=FakeModel(review_misses=[("responds",), ()], explanation_extras=[extra]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    first, second = backend.proposals[0]["review"]["history"]
    assert first["score"] == 80 and first["passed"] is False and first["blocking"] == ["변경 이벤트 미대응"]
    assert second["passed"] is True


def test_review_switches_method_when_the_score_does_not_improve():
    ctx, backend, _, _ = make_context(model=FakeModel(review_misses=[BAD, BAD, ()]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    history = backend.proposals[0]["review"]["history"]
    assert [h["action"] for h in history[:2]] == ["REWRITE", "NEXT_CANDIDATE"]
    assert backend.proposals[0]["candidate"]["location_id"] == 3


def test_missing_citation_with_collected_evidence_is_rewritten_not_searched_again():
    from app.graph.nodes import score_review
    from app.graph.schemas import ReviewChecks

    checklist = [{"constraint": c, "status": "PASS", "evidenceIds": ["x#1"]} for c in HARD_CONSTRAINTS]
    checklist[-1] = {"constraint": "WEATHER", "status": "WARN", "evidenceIds": []}
    text = "우천으로 성수 스튜디오로 옮깁니다(13시 이후 비 80%)."
    plan = {"candidate": SEONGSU, "explanation": text, "checklist": checklist, "unresolved": []}
    yes = QuotedCheck(found=True, quote=text)
    checks = ReviewChecks(change=yes, reason=yes, responds=yes, rejected_element=yes, cost_reason=yes)
    state = {"candidates": [SEONGSU], "event": {"detail": "13시 이후 비 80%"}, "info_retries": 0}
    assert score_review(checks, plan, state)["action"] == "MORE_EVIDENCE"
    state["hard_constraints"] = [{"constraint": "WEATHER", "evidence_ids": ["safety-disaster-weather#2"]}]
    scored = score_review(checks, plan, state)
    assert scored["action"] == "REWRITE" and "safety-disaster-weather#2" in " ".join(scored["feedback"])


def test_evidence_score_caps_categories_without_evidence():
    checklist = [{"constraint": c, "status": "PASS", "evidenceIds": ["x#1"]} for c in HARD_CONSTRAINTS]
    assert evidence_score(checklist) == (20, [], [])
    checklist[0] = {"constraint": "CONTRACT", "status": "WARN", "evidenceIds": []}
    checklist[1] = {"constraint": "SCHEDULE", "status": "WARN", "evidenceIds": ["x#2"]}
    assert evidence_score(checklist) == (12, ["SCHEDULE"], ["CONTRACT"])


def test_fact_problems_catch_wrong_numbers_and_cost_claims():
    state = {"candidates": [SEONGSU, PAJU], "plan_set": {"current": {"cost": 300000}}, "event": {"detail": "13시 이후 비"}}
    good = "성수 스튜디오, 14:00~16:00, 14km, 추가 비용 150,000원(450,000원)"
    assert fact_problems(good, SEONGSU, state) == []
    wrong = "성수 스튜디오, 15:30 시작, 5km, 추가 비용이 없습니다."
    problems = fact_problems(wrong, SEONGSU, state)
    assert len(problems) == 3 and any("추가 비용이 없다고" in p for p in problems)


def test_rejected_place_named_in_the_rejection_reason_is_not_a_fact_error():
    # 거절 사유를 풀어 쓰며 거절된 파주의 이름을 적어도 사실 오류가 아니다.
    state = {
        "candidates": [SEONGSU, PAJU],
        "plan_set": {"current": {"cost": 300000}, "options": [{"location": {"id": 3, "name": "파주 세트장"}}]},
        "event": {"detail": "13시 이후 비"},
        "last_rejection": {"reason": "파주 세트장은 장면 의도와 맞지 않음", "location_id": 3},
    }
    text = "파주 세트장이 장면 의도에 맞지 않는다는 거절을 반영해 성수 스튜디오로 옮깁니다."
    assert fact_problems(text, SEONGSU, state) == []
    # 거절된 안이 다른 장소였어도, 승인자가 사유에 적은 장소 이름은 설명에 쓸 수 있다.
    state["last_rejection"]["location_id"] = 102
    assert fact_problems(text, SEONGSU, state) == []
    assert fact_problems(text + " 짐벌 세트도 씁니다.", SEONGSU, state) != []


def test_mentions_checks_the_explanation_when_the_model_copies_the_event():
    state = {"candidates": [SEONGSU, PAJU], "event": {"detail": "13시 이후 한강 강수확률 80%"}}
    text = "성수 스튜디오 실내 촬영으로 강수확률 80%의 우천을 피했습니다."
    copied = QuotedCheck(found=True, quote="13시 이후 한강 강수확률 80%")
    assert mentions(copied, text, state["event"]["detail"], state)
    assert not mentions(copied, "성수 스튜디오로 옮깁니다.", state["event"]["detail"], state)
    # 사유를 밝히지 않은 거절 언급은 인용이 설명에 있어도 사유의 낱말이 없어 아니오다.
    vague = QuotedCheck(found=True, quote="직전 의견도 반영했습니다")
    assert not mentions(vague, "직전 의견도 반영했습니다. 파주 세트장으로 옮깁니다.", "성수 스튜디오 공사 소음", state)


def test_quoted_rejects_quotes_not_in_the_explanation():
    text = "우천으로 성수 스튜디오로 옮깁니다."
    assert quoted(QuotedCheck(found=True, quote="성수 스튜디오로 옮깁니다"), text)
    assert not quoted(QuotedCheck(found=True, quote="직전 거절 사유인 소음을 해결했습니다"), text)
    assert not quoted(QuotedCheck(found=False, quote=""), text)


def test_explanation_naming_another_candidate_is_rewritten_once():
    ctx, backend, _, _ = make_context(model=FakeModel(explanation_extras=["짐벌 세트도 챙깁니다."]))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    assert ctx.model.structured_calls.count("PlanExplanation") == 2
    assert "짐벌 세트" not in proposal["explanation"]
    assert not any(u.startswith("설명 확인 필요") for u in proposal["unresolved"])


def test_explanation_still_wrong_after_rewrite_is_blocked_by_review():
    # 다시 써도 다른 후보의 장비를 적으면 미확정 항목에 올리고, 자체 검토가 사실 오류로 통과를 막아 다시 쓰게 한다.
    ctx, backend, _, _ = make_context(model=FakeModel(explanation_extras=["짐벌 세트도 챙깁니다."] * 2))
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    history = backend.proposals[0]["review"]["history"]
    assert history[0]["blocking"] == ["설명의 사실 오류"] and history[-1]["passed"] is True
    assert "짐벌 세트" not in backend.proposals[0]["explanation"]


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


def test_candidate_places_come_from_current_plan_and_options():
    plan_set = {
        "current": {"location": {"name": "한강 공원"}},
        "options": [{"location": {"name": "한강 공원"}}, {"location": {"name": "파주 세트장"}}, {"optionNo": 3}],
    }
    assert candidate_places(plan_set) == ["한강 공원", "파주 세트장"]


def test_clauses_for_other_places_are_not_evidence():
    places = ["한강 공원", "파주 세트장"]
    # 북촌, 광화문, 남산의 비행금지구역 조항은 한강과 파주 재계획의 근거가 아니다.
    assert not applies_to_places({"locations": ["북촌", "광화문", "남산"]}, places)
    assert applies_to_places({"locations": ["파주"]}, places)
    assert applies_to_places({"locations": ["한강공원"]}, places)
    # 적용 장소가 없는 법령이나 사내 규정, 후보 장소를 모르는 경우는 그대로 둔다.
    assert applies_to_places({"locations": []}, places)
    assert applies_to_places({"locations": ["북촌"]}, [])


def test_citation_must_match_document_type_and_not_be_an_intro():
    law = {"doc_type": "LAW", "heading": "제53조 연장 근로의 제한"}
    permit_hours = {"doc_type": "PERMIT", "heading": "허가 시간"}
    assert counts_as_evidence("LAW", law)
    assert not counts_as_evidence("SCHEDULE", law)
    assert counts_as_evidence("SCHEDULE", permit_hours)
    assert not counts_as_evidence("NO_FLY_ZONE", {"doc_type": "NO_FLY", "heading": "개요"})


class OmittingModel(FakeModel):
    """제약 정리에서 정해 둔 범주를 비워 두는 가짜 모델입니다. 실제 로그에서 본 누락(재난 조항, 재수집 때 날씨 조항)을 흉내 낸다."""

    def __init__(self, omit_rounds, *, recheck=True, explain_omit=(), **kwargs):
        super().__init__(**kwargs)
        self.omit_rounds = [set(o) for o in omit_rounds]
        self.recheck = recheck
        self.explain_omit = set(explain_omit)
        self.summaries = 0
        self.rechecks = 0

    async def structured(self, ctx, messages, schema):
        result = await super().structured(ctx, messages, schema)
        if schema is ConstraintSet and "재확인" in _task_line(messages):
            self.rechecks += 1
            return result if self.recheck else ConstraintSet(findings=[], thought=THOUGHT)
        if schema is ConstraintSet:
            omit = self.omit_rounds[min(self.summaries, len(self.omit_rounds) - 1)]
            self.summaries += 1
            findings = [
                ConstraintFinding(constraint=f.constraint, summary="", evidence_ids=[]) if f.constraint in omit else f
                for f in result.findings
            ]
            return ConstraintSet(findings=findings, thought=THOUGHT)
        if schema is PlanExplanation and self.explain_omit:
            for item in result.checklist:
                if item.constraint in self.explain_omit:
                    item.evidence_ids = []
        return result


ALERT = {"type": "HEAVY_RAIN", "region": "서울", "message": "호우 경보"}


def test_empty_category_is_rechecked_from_collected_clauses_without_searching_again():
    backend = FakeBackendState(disaster_alerts=[ALERT])
    model = OmittingModel([{"DISASTER"}])
    ctx, _, _, _ = make_context(backend, model=model)
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return (await graph.aget_state(CONFIG)).values

    values = run(scenario())
    disaster = next(h for h in values["hard_constraints"] if h["constraint"] == "DISASTER")
    assert disaster["evidence_ids"] == ["safety-disaster-weather#1"]
    # 다시 검색하지 않고(제약 정리 1번) 받은 조항에서 고르기만 한다.
    assert model.rechecks == 1 and model.summaries == 1


def test_recollection_keeps_earlier_citations_and_stops_when_nothing_new_is_found():
    backend = FakeBackendState(disaster_alerts=[ALERT])
    # 근거 말고는 고칠 곳이 없도록 비용 이유를 설명에 넣는다.
    cost = ["추가 비용 150,000원은 실내 스튜디오 대관료 때문에 듭니다."] * 5
    model = OmittingModel(
        [{"DISASTER"}, {"DISASTER", "WEATHER"}], recheck=False, explain_omit={"DISASTER"}, explanation_extras=cost
    )
    ctx, _, _, _ = make_context(backend, model=model)
    graph, _ = compile_graph(ctx)

    async def scenario():
        await graph.ainvoke(initial_state(), CONFIG, context=ctx)
        return (await graph.aget_state(CONFIG)).values

    values = run(scenario())
    weather = next(h for h in values["hard_constraints"] if h["constraint"] == "WEATHER")
    # 두 번째 정리에서 날씨 조항을 빠뜨려도 첫 번째에서 찾은 근거가 남는다.
    assert weather["evidence_ids"] == ["safety-disaster-weather#2"]
    assert values["evidence_stalled"] is True
    assert model.summaries == 2
    # 남은 사유가 더 구할 수 없는 근거뿐이라 1회차에서 승인 요청으로 넘어가고, 빈 범주는 미확정 항목에 남는다.
    proposal = backend.proposals[0]
    assert proposal["review"]["rounds"] == 1 and proposal["review"]["passed"] is False
    assert "DISASTER 근거 조항 확인 필요" in proposal["unresolved"]


def test_permit_for_another_place_is_not_evidence_for_the_chosen_plan():
    # 한강에만 적용되는 허가 조항은 후보 장소(한강 현재안)로는 수집되지만, 성수 안의 근거는 아니다.
    backend = FakeBackendState(hit_overrides={"contract-actor-a-v3#1": {"doc_type": "PERMIT", "locations": ["한강"]}})
    model = OmittingModel([set()])
    ctx, _, _, _ = make_context(backend, model=model)
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    proposal = backend.proposals[0]
    assert proposal["candidate"]["location_id"] == SEONGSU["location"]["id"]
    schedule = next(item for item in proposal["checklist"] if item["constraint"] == "SCHEDULE")
    assert "contract-actor-a-v3#1" not in schedule["evidence_ids"]
    # 그 조항이 유일한 근거였던 범주는 성수에 맞는 조항에서 다시 고르게 한 번 묻는다.
    assert model.rechecks >= 1


def test_no_fly_list_for_another_place_still_counts_for_the_chosen_plan():
    # 비행금지 안내는 피해야 할 장소 목록이라, 다른 후보 장소(한강)를 적은 조항도 성수 안의 비행금지 근거가 된다.
    backend = FakeBackendState(hit_overrides={"no-fly-zone-notice#2": {"locations": ["한강"]}})
    ctx, _, _, _ = make_context(backend)
    graph, _ = compile_graph(ctx)
    run(graph.ainvoke(initial_state(), CONFIG, context=ctx))
    no_fly = next(item for item in backend.proposals[0]["checklist"] if item["constraint"] == "NO_FLY_ZONE")
    assert no_fly["evidence_ids"] == ["no-fly-zone-notice#2"]


def test_recheck_files_clauses_under_their_own_category_when_the_model_mislabels_it():
    from app.graph.nodes import recheck_empty_categories

    class MislabelingModel(FakeModel):
        async def structured(self, ctx, messages, schema):
            # 일정 칸의 계약 조항을 고르고 범주 이름은 사건 종류(DISASTER)로 적는다.
            return ConstraintSet(
                findings=[ConstraintFinding(constraint="DISASTER", summary="호우 경보로 촬영 불가", evidence_ids=["c#1"])],
                thought=THOUGHT,
            )

    ctx, _, _, _ = make_context(model=MislabelingModel())
    evidence = {"c#1": {"doc_type": "CONTRACT", "heading": "제5조 촬영 시간", "title": "계약서", "text": "09시부터 16시까지"}}
    findings = {"SCHEDULE": {"constraint": "SCHEDULE", "summary": "", "evidence_ids": []}}
    filled = run(recheck_empty_categories(ctx, {"event": {}}, findings, evidence, only={"SCHEDULE"}))
    assert filled == ["SCHEDULE"]
    assert findings["SCHEDULE"]["evidence_ids"] == ["c#1"]
    assert "호우" not in findings["SCHEDULE"]["summary"]
