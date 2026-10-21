"""재계획 그래프의 노드입니다. 한 번의 루프는 최적안 하나만 냅니다."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from app.graph.common import ToolCallError, call_tool_or_raise, harnessed, run_tool_loop
from app.graph.schemas import (
    AlternativeKeywords,
    ConstraintSet,
    ImpactSummary,
    PlanExplanation,
    PlanReview,
    RejectionPlan,
    WeightAdjustment,
)
from app.graph.state import DEFAULT_WEIGHTS, HARD_CONSTRAINTS
from app.harness.context import Section, fit_sections, summarize_loops
from app.harness.instructions import render
from app.harness.limits import NO_FEASIBLE_PLAN, STOP_MESSAGES, stop_condition
from app.runtime import RunContext

# LLM이 고를 수 있는 도구 목록이다. 데이터를 바꾸는 도구는 넣지 않는다.
IMPACT_TOOLS = [
    "business_find_impacted_entities",
    "business_get_entity_context",
    "business_get_availability",
    "business_get_weather",
    "business_get_disaster_alerts",
]
CONSTRAINT_TOOLS = ["rag_search_regulation", "rag_search_contract_clause"]

MEMORY_NAMESPACE = ("shortcut", "rejections")
ISSUE_LABELS = {"LOCATION": "장소", "TIME": "시간대", "EQUIPMENT": "장비", "COST": "비용", "OTHER": "기타"}
# 문제 요소마다 만들 수 있는 제약 유형이다. 고르지 않은 요소를 건드리는 제약은 버린다.
ISSUE_CONSTRAINT_TYPES = {
    "LOCATION": {"EXCLUDE_LOCATION", "EXCLUDE_LOCATION_TIME", "REQUIRE_INDOOR"},
    "TIME": {"EXCLUDE_TIME", "LATEST_END"},
    "EQUIPMENT": {"EXCLUDE_EQUIPMENT"},
    "COST": {"MAX_EXTRA_COST"},
}
# 새 루프가 시작되면 자체 검토 기록을 비운다. 앞 루프의 점수와 피드백은 다른 안에 대한 것이다.
REVIEW_RESET = {
    "review_round": 0,
    "review_history": [],
    "best_review": None,
    "review_feedback": [],
    "review_skipped": [],
    "validated_hash": None,
    "review_result": None,
}
# 4안 후보로 올릴 대체 장소 수다. 많이 올리면 조합이 늘어 평가 결과가 길어지고 판단이 흐려진다.
MAX_ALTERNATIVES = 3
# 가중치가 한쪽으로 쏠리면 다른 기준이 사실상 무시되므로 각 가중치를 0.05~0.6 사이로 묶는다.
MIN_WEIGHT, MAX_WEIGHT = 0.05, 0.6
# 규정 검색을 실행하는 총 횟수 상한이다. 세 번 찾고도 근거가 없으면 미확정 항목으로 넘긴다.
MAX_INFO_RETRIES = 3


def _system() -> str:
    return render("planner_system")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def describe(candidate: dict[str, Any]) -> str:
    """후보안을 사람이 읽는 한 줄로 바꿉니다."""
    names = ", ".join(item["name"] for item in candidate["equipment"]["items"])
    return (
        f"장소 {candidate['location']['name']}({candidate['location']['optionNo']}안), "
        f"장비 {names}({candidate['equipment']['optionNo']}안), "
        f"시간 {candidate['time']['start']}~{candidate['time']['end']}({candidate['time']['optionNo']}안), "
        f"종합 점수 {candidate['totalScore']}"
    )


def explanation_problems(
    text: str, choice: dict[str, Any], candidates: list[dict[str, Any]], current: dict[str, Any]
) -> list[str]:
    """설명에 선택한 장소가 빠졌거나 선택하지 않은 장소나 장비 이름이 들어갔는지 봅니다.
    원래 확정안의 이름은 무엇이 바뀌었는지 설명하는 데 필요하므로 허용합니다."""
    locations = {c["location"]["id"]: c["location"]["name"] for c in candidates}
    equipment = {item["id"]: item["name"] for c in candidates for item in c["equipment"]["items"]}
    current_location = current.get("location") or {}
    allowed = {
        choice["location"]["name"],
        *(item["name"] for item in choice["equipment"]["items"]),
        current_location.get("name") or locations.get(current_location.get("id"), ""),
        *(item.get("name") or equipment.get(item.get("id"), "") for item in current.get("equipment") or []),
    } - {""}
    problems = []
    if choice["location"]["name"] not in text:
        problems.append(f"설명에 선택한 장소가 없습니다: {choice['location']['name']}")
    # "추가 조명 패키지" 안의 "조명 패키지"처럼 허용된 이름에 포함된 이름을 잘못 잡지 않도록 허용된 이름을 먼저 지운다.
    rest = text
    for name in sorted(allowed, key=len, reverse=True):
        rest = rest.replace(name, " ")
    foreign = [name for name in sorted({*locations.values(), *equipment.values()} - allowed) if name in rest]
    if foreign:
        problems.append(f"설명에 선택하지 않은 장소나 장비가 있습니다: {', '.join(foreign)}")
    return problems


def to_mcp_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "location_id": candidate["location"]["id"],
        "equipment_ids": [item["id"] for item in candidate["equipment"]["items"]],
        "start": candidate["time"]["start"],
        "end": candidate["time"]["end"],
        "source": {
            "location": candidate["location"]["optionNo"],
            "equipment": candidate["equipment"]["optionNo"],
            "time": candidate["time"]["optionNo"],
        },
    }


def _evidence_lines(evidence: dict[str, dict[str, Any]], limit_chars: int = 220) -> str:
    return (
        "\n".join(f"[{cid}] {hit['title']} / {hit['heading']}: {hit['text'][:limit_chars]}" for cid, hit in evidence.items())
        or "검색된 근거 없음"
    )


def repeats_rejection(candidate: dict[str, Any], rejected: list[dict[str, Any]]) -> bool:
    """이전에 거절된 안에서 문제로 지목된 요소를 그대로 가진 후보인지 봅니다. 문제로 고르지 않은 요소는 같아도 됩니다."""
    for plan in rejected:
        issues = set(plan.get("issues") or [])
        if "LOCATION" in issues and candidate["location"]["id"] == plan["location_id"]:
            return True
        if "TIME" in issues and (candidate["time"]["start"], candidate["time"]["end"]) == (plan["start"], plan["end"]):
            return True
        if "EQUIPMENT" in issues and sorted(i["id"] for i in candidate["equipment"]["items"]) == sorted(plan["equipment_ids"]):
            return True
        # 비용이 문제였다면 그보다 싸지 않은 안은 같은 이유로 다시 거절된다.
        if "COST" in issues and candidate["extraCost"] >= plan["extra_cost"]:
            return True
    return False


def pick_after_rejection(feasible: list[dict[str, Any]], rejection: dict[str, Any] | None) -> dict[str, Any] | None:
    """거절 사유에서 고른 문제 요소만 바꾸고 나머지 요소는 거절된 안과 같은 후보를 먼저 고릅니다.

    문제 삼지 않은 요소까지 바뀌면 이미 동의한 승인자가 다시 판단해야 하고, 사유를 보완한 안이라는 점도 흐려진다.
    같은 수의 요소를 유지하는 후보끼리는 종합 점수가 높은 쪽을 고른다.
    """
    if not feasible:
        return None
    if not rejection or not rejection.get("issues"):
        return feasible[0]
    issues = set(rejection["issues"])

    def kept(candidate: dict[str, Any]) -> int:
        count = 0
        if "LOCATION" not in issues and candidate["location"]["id"] == rejection["location_id"]:
            count += 1
        if "TIME" not in issues and (candidate["time"]["start"], candidate["time"]["end"]) == (
            rejection["start"],
            rejection["end"],
        ):
            count += 1
        if "EQUIPMENT" not in issues and sorted(i["id"] for i in candidate["equipment"]["items"]) == sorted(
            rejection["equipment_ids"]
        ):
            count += 1
        return count

    return max(feasible, key=lambda c: (kept(c), c["totalScore"]))


def constraints_for_issues(
    proposed: list[dict[str, Any]], issues: list[str], candidate: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """모델이 만든 제약 가운데 승인자가 고른 문제 요소에 해당하는 것만 남기고, 버린 제약도 함께 돌려줍니다.

    프롬프트로 "고르지 않은 요소는 바꾸지 말라"고 해도 모델이 시간대 제외를 덧붙여 모든 후보를 막은 적이 있어 코드로 강제한다.
    남은 제약이 없으면 문제 요소마다 거절된 안을 기준으로 한 기본 제약을 만든다.
    """
    if not issues or "OTHER" in issues:
        return proposed, []
    allowed = set().union(*(ISSUE_CONSTRAINT_TYPES.get(issue, set()) for issue in issues))
    kept = [c for c in proposed if c["type"] in allowed]
    dropped = [c for c in proposed if c["type"] not in allowed]
    covered = {issue for issue in issues if any(c["type"] in ISSUE_CONSTRAINT_TYPES.get(issue, set()) for c in kept)}
    for issue in issues:
        if issue in covered:
            continue
        if issue == "LOCATION":
            kept.append({"type": "EXCLUDE_LOCATION", "location_id": candidate["location"]["id"]})
        elif issue == "TIME":
            kept.append({"type": "EXCLUDE_TIME", "from_time": candidate["time"]["start"], "to_time": candidate["time"]["end"]})
        elif issue == "COST":
            kept.append({"type": "MAX_EXTRA_COST", "amount": max(candidate["extraCost"] - 1, 0)})
        # 장비는 어떤 장비가 문제인지 사유 없이 고를 수 없어 기본 제약을 만들지 않는다.
    return kept, dropped


@harnessed("detect_change", "변경 감지")
async def detect_change(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """변경 이벤트를 접수하고 오후 블록의 1/2/3안과 현재 데이터 버전을 읽습니다."""
    plan_set = await call_tool_or_raise(ctx, "business_get_plan_set", {"shoot_day_id": state["shoot_day_id"]})
    notes = []
    if ctx.store is not None:
        for item in await ctx.store.asearch(MEMORY_NAMESPACE, limit=5):
            value = item.value
            notes.append(
                f"과거 거절: {value['role']} / {value['location_name']} {value['start']}~{value['end']} / {value['reason']}"
            )
    event = state["event"]
    return {
        "plan_set": plan_set,
        "data_version": plan_set["dataVersion"],
        "memory_notes": notes,
        "weights": dict(DEFAULT_WEIGHTS),
        "_detail": f"{event['type']} 접수: {event['detail']}",
    }


@harnessed("analyze_impact", "영향 분석")
async def analyze_impact(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """모델이 온톨로지와 날씨, 재난 문자, 가용 자원 도구 가운데 필요한 것을 골라 영향 범위를 묶습니다."""
    plan_set, event = state["plan_set"], state["event"]
    user = render(
        "impact_analysis",
        event=_json(event),
        block=_json(plan_set["block"]),
        block_node=f"BLOCK:{state['shoot_day_id']}-{plan_set['block']['code']}",
        current=_json(plan_set["current"]),
        memory="\n".join(state.get("memory_notes") or []) or "없음",
    )
    outcomes, _ = await run_tool_loop(ctx, _system(), user, IMPACT_TOOLS, ctx.settings.limits.max_node_tool_rounds)

    conditions: dict[str, Any] = {}
    graph_results = []
    for outcome in outcomes:
        if not outcome.ok:
            continue
        key = outcome.name.removeprefix("business_")
        if key in {"get_weather", "get_disaster_alerts", "get_availability"}:
            conditions[key.removeprefix("get_")] = outcome.data
        else:
            graph_results.append(outcome.data)
    # 재계획 판단에 반드시 필요한 조건은 모델이 빠뜨려도 Harness가 직접 채워 다음 단계가 빈 데이터로 판단하지 않게 한다.
    for key, tool in (
        ("weather", "get_weather"),
        ("disaster_alerts", "get_disaster_alerts"),
        ("availability", "get_availability"),
    ):
        if key not in conditions:
            conditions[key] = await call_tool_or_raise(ctx, f"business_{tool}", {"shoot_day_id": state["shoot_day_id"]})

    summary = await ctx.model.structured(
        ctx,
        [
            SystemMessage(_system()),
            HumanMessage(
                render(
                    "impact_summary",
                    event=_json(event),
                    graph=_json(graph_results)[:3000],
                    alerts=_json(conditions["disaster_alerts"]),
                )
            ),
        ],
        ImpactSummary,
    )
    block_actor_ids = set(plan_set["block"]["actorIds"])
    contract_ids = sorted(
        actor["contractDocId"] for actor in conditions["availability"]["actors"] if actor["id"] in block_actor_ids
    )
    impacted = summary.model_dump()
    impacted["contract_doc_ids"] = contract_ids
    return {
        "impacted_entities": impacted,
        "conditions": conditions,
        "_detail": f"영향 엔티티 {len(summary.impacted)}개, 위험 {len(summary.risks)}개, 계약서 {', '.join(contract_ids)}",
    }


@harnessed("collect_constraints", "제약 수집")
async def collect_constraints(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """모델이 규정 검색 도구를 골라 하드 제약 범주별 원문 근거를 모읍니다."""
    impacted = state["impacted_entities"]
    user = render(
        "constraint_collection",
        event=_json(state["event"]),
        contracts=", ".join(impacted["contract_doc_ids"]),
        risks="\n".join(impacted["risks"]) or "없음",
        alerts=_json(state["conditions"]["disaster_alerts"]),
        missing=", ".join(state.get("missing_info") or []) or "없음",
    )
    outcomes, _ = await run_tool_loop(ctx, _system(), user, CONSTRAINT_TOOLS, ctx.settings.limits.max_node_tool_rounds)

    evidence = dict(state.get("evidence") or {})
    for outcome in outcomes:
        if outcome.ok:
            for hit in outcome.data:
                evidence[hit["chunk_id"]] = hit

    found = await ctx.model.structured(
        ctx,
        [SystemMessage(_system()), HumanMessage(render("constraint_summary", evidence=_evidence_lines(evidence)))],
        ConstraintSet,
    )
    findings = []
    for finding in found.findings:
        # 모델이 검색하지 않은 ID를 근거로 적으면 확인할 수 없으므로 실제로 받은 chunk_id만 남긴다.
        cited = [cid for cid in finding.evidence_ids if cid in evidence]
        findings.append({"constraint": finding.constraint, "summary": finding.summary, "evidence_ids": cited})
    covered = {f["constraint"] for f in findings if f["evidence_ids"]}
    missing = [c for c in HARD_CONSTRAINTS if c not in covered]
    return {
        "evidence": evidence,
        "hard_constraints": findings,
        "missing_info": missing,
        "info_retries": state.get("info_retries", 0) + 1,
        "_detail": f"근거 {len(evidence)}건, 근거 부족 범주 {', '.join(missing) or '없음'}",
    }


@harnessed("reevaluate_plans", "1/2/3안 재평가")
async def reevaluate_plans(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """감독 지시가 있으면 가중치를 조정하고, 업무 규칙 엔진으로 27개 조합을 다시 평가합니다."""
    weights = dict(state.get("weights") or DEFAULT_WEIGHTS)
    rationale = state.get("weight_rationale", "")
    instruction = (state["event"].get("instruction") or "").strip()
    if instruction and not rationale:
        adjusted = await ctx.model.structured(
            ctx,
            [
                SystemMessage(_system()),
                HumanMessage(render("weight_adjust", instruction=instruction, weights=_json(weights))),
            ],
            WeightAdjustment,
        )
        raw = {key: min(max(getattr(adjusted, key), MIN_WEIGHT), MAX_WEIGHT) for key in DEFAULT_WEIGHTS}
        total = sum(raw.values())
        weights = {key: round(value / total, 3) for key, value in raw.items()}
        rationale = adjusted.rationale

    result = await call_tool_or_raise(
        ctx,
        "business_evaluate_plans",
        {
            "shoot_day_id": state["shoot_day_id"],
            "weights": weights,
            "extra_constraints": state.get("extra_constraints") or [],
            "exclude_hashes": state.get("failed_hashes") or [],
        },
    )
    top = result["candidates"][0] if result["candidates"] else None
    detail = f"실행 가능 후보 {result['feasibleCount']}개"
    if top and top["feasible"]:
        detail += f", 1위 {describe(top)}"
    return {
        "weights": weights,
        "weight_rationale": rationale,
        "candidates": result["candidates"],
        "feasible_count": result["feasibleCount"],
        "data_version": result["dataVersion"],
        "_detail": detail,
    }


@harnessed("compose_plan", "최적안 구성")
async def compose_plan(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """점수가 가장 높은 실행 가능 후보 하나를 고르고 승인자가 읽을 설명과 체크리스트를 만듭니다."""
    failed = set(state.get("failed_hashes") or [])
    skipped = set(state.get("review_skipped") or [])
    feasible = [c for c in state["candidates"] if c["feasible"] and c["hash"] not in failed | skipped]
    # 모델이 거절 사유를 좁은 제약으로 바꿔도, 문제로 지목된 요소가 같은 안은 승인자에게 다시 보이지 않게 거른다.
    repeats = [c["hash"] for c in feasible if repeats_rejection(c, state.get("rejected_plans") or [])]
    feasible = [c for c in feasible if c["hash"] not in repeats]
    choice = pick_after_rejection(feasible, state.get("last_rejection"))
    if choice is None:
        if repeats:
            # 엔진은 상위 후보만 돌려주므로, 거른 후보를 빼고 다시 평가해야 뒤에 있던 후보가 올라온다.
            return {
                "selected_plan": None,
                "repeat_filtered": True,
                "failed_hashes": [*(state.get("failed_hashes") or []), *repeats],
                "_detail": f"거절된 안과 같은 요소를 가진 후보 {len(repeats)}개를 걸러 다시 평가합니다",
            }
        return {"selected_plan": None, "repeat_filtered": False, "_detail": "남은 실행 가능 후보 없음"}

    evidence = state.get("evidence") or {}
    others = [describe(c) for c in state["candidates"][1:4]]
    sections = [
        # 검토 단계와 같은 사실(거리, 실내 여부, 비용)을 줘야 검토에서 지적한 점을 설명에 반영할 수 있다.
        # 따로 떼어 두면 비교 후보와 섞어 읽는 경우가 있어 선택한 후보 안에 함께 적는다.
        Section(
            "선택한 후보",
            f"{describe(choice)}\n항목별 점수: {_json(choice['softScores'])}\n{review_facts(choice)}",
            0,
        ),
        Section("변경 이벤트", _json(state["event"]), 0),
        Section("자체 검토 피드백 (반드시 반영)", "\n".join(state.get("review_feedback") or []) or "없음", 0),
        Section("하드 제약과 근거 요약", _json(state.get("hard_constraints") or []), 1),
        Section("가중치", f"{_json(state['weights'])} {state.get('weight_rationale', '')}", 1),
        Section("이전 루프", summarize_loops(state.get("loop_summaries") or []), 1),
        Section("추가 제약", _json(state.get("extra_constraints") or []), 1),
        Section("근거 조항", _evidence_lines(evidence), 2),
        Section("비교 후보", "\n".join(others) or "없음", 3),
    ]
    body = fit_sections(sections, ctx.settings.context_token_budget)
    messages = [SystemMessage(_system()), HumanMessage(render("compose_plan", context=body))]
    explained = await ctx.model.structured(ctx, messages, PlanExplanation)
    current = state["plan_set"].get("current") or {}
    problems = explanation_problems(explained.explanation, choice, state["candidates"], current)
    if problems:
        # 다른 후보의 장비를 섞어 적으면 승인자가 잘못 판단하므로, 무엇이 틀렸는지 알려 주고 한 번 다시 쓰게 한다.
        correction = HumanMessage(
            f"방금 쓴 설명에 문제가 있습니다. {' '.join(problems)}\n"
            f"선택한 후보는 {describe(choice)}입니다. 이 후보만 설명하도록 다시 쓰세요.\n방금 쓴 설명: {explained.explanation}"
        )
        explained = await ctx.model.structured(ctx, [*messages, correction], PlanExplanation)
        problems = explanation_problems(explained.explanation, choice, state["candidates"], current)

    checklist = {}
    for entry in explained.checklist:
        cited = [cid for cid in entry.evidence_ids if cid in evidence]
        checklist[entry.constraint] = {
            "constraint": entry.constraint,
            "status": entry.status,
            "note": entry.note,
            "evidenceIds": cited,
        }
    unresolved = list(explained.unresolved)
    # 다시 써도 틀리면 승인자가 직접 확인하도록 미확정 항목에 올린다.
    unresolved.extend(f"설명 확인 필요, {problem}" for problem in problems)
    for constraint in HARD_CONSTRAINTS:
        item = checklist.get(constraint)
        # 근거 없이 통과라고 적은 항목은 검증할 수 없으므로 경고로 낮추고 사람이 확인할 항목에 올린다.
        if item is None or not item["evidenceIds"]:
            checklist[constraint] = {
                "constraint": constraint,
                "status": "WARN",
                "note": (item or {}).get("note") or "근거 조항을 찾지 못했습니다",
                "evidenceIds": [],
            }
            unresolved.append(f"{constraint} 근거 조항 확인 필요")

    missing = list(explained.missing) if explained.needs_more_info else []
    return {
        "selected_plan": {
            "hash": choice["hash"],
            "candidate": choice,
            "explanation": explained.explanation,
            "checklist": [checklist[c] for c in HARD_CONSTRAINTS],
            "unresolved": sorted(set(unresolved)),
        },
        "missing_info": missing,
        "repeat_filtered": False,
        "_detail": describe(choice) + (f" (거절된 안과 겹치는 후보 {len(repeats)}개 제외)" if repeats else ""),
    }


@harnessed("validation_gate", "검증 게이트")
async def validation_gate(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """판정은 업무 규칙 엔진이 하고, 게이트는 위반안이 승인 단계로 넘어가지 못하게 막기만 합니다."""
    plan = state["selected_plan"]
    result = await call_tool_or_raise(
        ctx,
        "business_validate_plan",
        {
            "shoot_day_id": state["shoot_day_id"],
            "candidate": to_mcp_candidate(plan["candidate"]),
            "data_version": state["data_version"],
            "extra_constraints": state.get("extra_constraints") or [],
        },
    )
    if result["stale"]:
        return {"selected_plan": None, "gate_result": "STALE", "_detail": "데이터 버전이 바뀌어 재평가합니다"}
    if not result["valid"]:
        codes = [v["code"] for v in result["violations"]]
        return {
            "selected_plan": None,
            "gate_result": "VIOLATION",
            "failed_hashes": [*(state.get("failed_hashes") or []), plan["hash"]],
            "violations": [*(state.get("violations") or []), {"hash": plan["hash"], "codes": codes}],
            "_detail": f"위반 {', '.join(codes)}",
        }
    return {"gate_result": "PASS", "validated_hash": plan["hash"], "_detail": "하드 제약 위반 없음"}


def review_facts(candidate: dict[str, Any]) -> str:
    """검토 모델이 비용이나 날씨를 잘못 읽고 감점하지 않도록 엔진이 확인한 값을 그대로 적습니다."""
    warnings = ", ".join(w["message"] for w in candidate.get("warnings") or []) or "없음"
    return (
        "하드 제약 위반: 0건 (업무 규칙 엔진과 검증 게이트가 계약, 일정, 법규, 예산 상한, 비행 금지, 재난, 날씨를 모두 확인함)\n"
        f"이 안의 장소와 장비 비용: {candidate['cost']}원 (블록 예산 상한 이내), 현재 확정안 대비 추가 비용: {candidate['extraCost']}원\n"
        f"목동 기준 이동 거리: {candidate['distanceKm']}km, 실내 여부: {'실내' if candidate['location']['indoor'] else '야외'}\n"
        f"엔진 경고: {warnings}"
    )


@harnessed("self_review", "자체 검토")
async def self_review(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """승인 요청 전에 승인자 입장에서 안을 채점합니다. 통과 점수 미만이면 고쳐서 다시 검토하고,
    상한 회차에 닿으면 그때까지 가장 점수가 높았던 안으로 승인을 요청합니다."""
    limits = ctx.settings.limits
    plan = state["selected_plan"]
    candidate = plan["candidate"]
    round_no = state.get("review_round", 0) + 1
    checklist = "\n".join(
        f"{c['constraint']} {c['status']} 근거 {len(c['evidenceIds'])}건: {c['note']}" for c in plan["checklist"]
    )
    body = fit_sections(
        [
            Section("업무 규칙 엔진이 확인한 사실", review_facts(candidate), 0),
            Section("변경안", describe(candidate), 0),
            Section("엔진 항목별 점수(0~1)", _json(candidate["softScores"]), 0),
            Section("설명", plan["explanation"], 0),
            Section("하드 제약 체크리스트", checklist, 0),
            Section("미확정 항목", "\n".join(plan["unresolved"]) or "없음", 1),
            Section("변경 이벤트", _json(state["event"]), 1),
            Section("직전 거절", _json(state.get("last_rejection")) if state.get("last_rejection") else "없음", 0),
            Section("이전 검토 회차", _json(state.get("review_history") or []), 2),
        ],
        ctx.settings.context_token_budget,
    )
    review = await ctx.model.structured(
        ctx, [SystemMessage(_system()), HumanMessage(render("self_review", context=body))], PlanReview
    )
    breakdown = {k: getattr(review, k) for k in ("evidence", "rejection", "optimization", "explanation", "risk")}
    # 합계를 모델에게 맡기면 덧셈이 틀리는 경우가 있어 항목 점수를 코드가 더한다.
    score = sum(breakdown.values())
    history = [
        *(state.get("review_history") or []),
        {
            "round": round_no,
            "score": score,
            "hash": plan["hash"],
            "action": review.action,
            "breakdown": breakdown,
            "feedback": review.feedback,
        },
    ]
    best = state.get("best_review")
    if best is None or score > best["score"]:
        best = {"score": score, "round": round_no, "plan": plan}

    update: dict[str, Any] = {"review_round": round_no, "review_history": history, "best_review": best}
    if score >= limits.review_pass_score or round_no >= limits.max_review_rounds:
        passed = score >= limits.review_pass_score
        chosen = plan if passed else best["plan"]
        final_score = score if passed else best["score"]
        update.update(
            {
                "selected_plan": chosen,
                "review_next": "request_approval",
                "review_result": {
                    "score": final_score,
                    "passed": passed,
                    "threshold": limits.review_pass_score,
                    "rounds": round_no,
                    "chosenRound": round_no if passed else best["round"],
                    "history": history,
                },
                "_detail": f"{round_no}회차 {score}점, "
                + (
                    "통과"
                    if passed
                    else f"{limits.max_review_rounds}회 도달, 가장 높은 {best['round']}회차 {best['score']}점 안으로 승인 요청"
                ),
            }
        )
        return update

    action = review.action
    skipped = [*(state.get("review_skipped") or []), plan["hash"]]
    failed = set(state.get("failed_hashes") or [])
    has_other = any(c["feasible"] and c["hash"] not in failed and c["hash"] not in skipped for c in state["candidates"])
    previous = (state.get("review_history") or [])[-1:]
    # 같은 방법으로 고쳤는데 점수가 오르지 않았으면 같은 시도를 반복하지 않고 다른 방법으로 바꾼다.
    if previous and score <= previous[0]["score"] and action == previous[0]["action"]:
        action = "NEXT_CANDIDATE" if action != "NEXT_CANDIDATE" and has_other else "MORE_EVIDENCE"
    # 바꿀 후보가 없거나 근거 검색을 이미 다 쓴 경우에는 같은 안의 설명과 체크리스트를 고치는 쪽으로 돌린다.
    if action == "NEXT_CANDIDATE" and not has_other:
        action = "REWRITE"
    if action == "MORE_EVIDENCE" and state.get("info_retries", 0) >= MAX_INFO_RETRIES:
        action = "REWRITE"
    # 이력에는 모델이 제안한 행동이 아니라 실제로 실행한 행동을 남겨야 다음 회차의 정체 판단과 화면 표시가 맞는다.
    history[-1]["action"] = action
    update["review_feedback"] = review.feedback
    if action == "NEXT_CANDIDATE":
        update.update({"review_skipped": skipped, "review_next": "compose_plan"})
    elif action == "MORE_EVIDENCE":
        weak = [c["constraint"] for c in plan["checklist"] if c["status"] == "WARN" or not c["evidenceIds"]]
        update.update({"missing_info": weak or list(HARD_CONSTRAINTS), "review_next": "collect_constraints"})
    else:
        update["review_next"] = "compose_plan"
    labels = {"REWRITE": "설명과 근거 보완", "NEXT_CANDIDATE": "다른 조합으로 교체", "MORE_EVIDENCE": "규정 근거 추가 검색"}
    update["_detail"] = (
        f"{round_no}회차 {score}점, {limits.review_pass_score}점 미만이라 {labels[action]}: {'; '.join(review.feedback[:2])}"
    )
    return update


@harnessed("request_approval", "다중 승인 대기")
async def request_approval(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """근거 원문을 대조한 뒤 변경안을 등록하고 필수 승인자에게 승인을 요청합니다."""
    plan = state["selected_plan"]
    evidence = state.get("evidence") or {}
    cited_ids = sorted({cid for item in plan["checklist"] for cid in item["evidenceIds"]})
    originals: dict[str, str] = {}
    cited = []
    for cid in cited_ids:
        hit = evidence[cid]
        if hit["doc_id"] not in originals:
            originals[hit["doc_id"]] = await ctx.tools.read_resource("rag", f"rag://documents/{hit['doc_id']}")
        # 검색 결과가 색인 이후 바뀐 원문과 다르면 근거로 쓰지 않는다.
        if hit["text"] in originals[hit["doc_id"]]:
            cited.append(
                {
                    "id": cid,
                    "doc_id": hit["doc_id"],
                    "title": f"{hit['title']} / {hit['heading']}",
                    "text": hit["text"],
                    "doc_type": hit["doc_type"],
                }
            )

    candidate = plan["candidate"]
    loop_no = ctx.counter["loops"]
    outcome = await ctx.tools.call(
        ctx,
        "business_submit_proposal",
        {
            "task_id": state["task_id"],
            "event_id": state["event"]["id"],
            "shoot_day_id": state["shoot_day_id"],
            "loop_no": loop_no,
            "candidate": to_mcp_candidate(candidate),
            "score": candidate["totalScore"],
            "score_breakdown": candidate["softScores"],
            "weights": state["weights"],
            "explanation": plan["explanation"],
            "checklist": [
                {"constraint": c["constraint"], "status": c["status"], "note": c["note"], "evidence_ids": c["evidenceIds"]}
                for c in plan["checklist"]
            ],
            "evidence": cited,
            "unresolved": plan["unresolved"],
            "data_version": state["data_version"],
            "review": state.get("review_result"),
        },
        allowed=["business_submit_proposal"],
    )
    if not outcome.ok:
        # 등록 직전에 업무 데이터가 바뀌었거나 서버 재검증에서 위반이 나오면 작업을 실패시키지 않고 최신 데이터로 다시 평가한다.
        if outcome.error_code in {"VERSION_CONFLICT", "PLAN_INVALID"}:
            return {
                "selected_plan": None,
                "approvals": {},
                "failed_hashes": [*(state.get("failed_hashes") or []), plan["hash"]],
                "_detail": f"변경안 등록 거부({outcome.error_code}), 재평가합니다",
            }
        raise ToolCallError(outcome)
    created = outcome.data
    return {
        "approvals": {
            "proposal_id": created["proposalId"],
            "version_no": created["versionNo"],
            "required": created["requiredApprovers"],
            "decision": None,
        },
        "_detail": f"변경안 {created['versionNo']} 승인 요청: {', '.join(created['requiredApprovers'])}",
        "_events": [
            (
                "APPROVAL_REQUIRED",
                {
                    "proposalId": created["proposalId"],
                    "versionNo": created["versionNo"],
                    "requiredApprovers": created["requiredApprovers"],
                    "summary": describe(candidate),
                },
            )
        ],
    }


# 진행 이벤트를 받은 backend는 작업을 RUNNING으로 바꾸므로, 멈추러 들어가는 순간에는 시작 이벤트를 보내지 않아 WAITING_APPROVAL을 유지한다.
@harnessed("await_approval", "다중 승인 대기", event_node="request_approval", announce_start=False)
async def await_approval(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """승인 결과가 올 때까지 멈춥니다. 대기 중에는 LLM을 부르지 않고, 재개되면 이 노드부터 다시 실행됩니다."""
    approvals = dict(state["approvals"])
    decision = interrupt({"proposal_id": approvals["proposal_id"], "required": approvals["required"]})
    approvals.update({"decision": decision["decision"], "role": decision.get("role"), "reason": decision.get("reason")})
    update: dict[str, Any] = {"approvals": approvals}
    plan = state["selected_plan"]

    if decision["decision"] == "REJECTED":
        candidate = plan["candidate"]
        issues = decision.get("issues") or []
        rejection = await ctx.model.structured(
            ctx,
            [
                SystemMessage(_system()),
                HumanMessage(
                    render(
                        "rejection_to_constraint",
                        role=decision.get("role", ""),
                        reason=decision.get("reason", ""),
                        issues=", ".join(ISSUE_LABELS.get(i, i) for i in issues) or "선택 없음",
                        plan=describe(candidate),
                        location_id=candidate["location"]["id"],
                        start=candidate["time"]["start"],
                        end=candidate["time"]["end"],
                        equipment=_json(candidate["equipment"]["items"]),
                        extra_cost=candidate["extraCost"],
                    )
                ),
            ],
            RejectionPlan,
        )
        source = f"REJECTION:{decision.get('role', '')}"
        proposed = [{k: v for k, v in item.model_dump().items() if v is not None} for item in rejection.constraints]
        accepted, dropped = constraints_for_issues(proposed, issues, candidate)
        extras = [{**extra, "reason": decision.get("reason", ""), "source": source} for extra in accepted]
        if ctx.store is not None:
            await ctx.store.aput(
                MEMORY_NAMESPACE,
                f"{approvals['proposal_id']}-{decision.get('role')}",
                {
                    "role": decision.get("role"),
                    "location_name": candidate["location"]["name"],
                    "start": candidate["time"]["start"],
                    "end": candidate["time"]["end"],
                    "reason": decision.get("reason", ""),
                    "issues": issues,
                    "constraints": extras,
                },
            )
        ctx.counter["loops"] += 1
        ctx.counter["loop_elapsed_ms"] = 0
        rejected = {
            "role": decision.get("role"),
            "reason": decision.get("reason", ""),
            "issues": issues,
            "hash": plan["hash"],
            "location_id": candidate["location"]["id"],
            "equipment_ids": [i["id"] for i in candidate["equipment"]["items"]],
            "start": candidate["time"]["start"],
            "end": candidate["time"]["end"],
            "extra_cost": candidate["extraCost"],
        }
        update.update(
            {
                "extra_constraints": [*(state.get("extra_constraints") or []), *extras],
                "failed_hashes": [*(state.get("failed_hashes") or []), plan["hash"]],
                "last_rejection": {**rejected, "summary": rejection.summary},
                "rejected_plans": [*(state.get("rejected_plans") or []), rejected],
                "widen_search": "LOCATION" in issues and not state.get("alternatives_tried"),
                "loop_summaries": [
                    *(state.get("loop_summaries") or []),
                    f"루프 {ctx.counter['loops'] - 1}: {describe(candidate)} | 결과: {decision.get('role')} 거절({decision.get('reason')}) -> {rejection.summary}",
                ],
                **REVIEW_RESET,
                "selected_plan": None,
                "_detail": f"{decision.get('role')} 거절, 보완 방향: {rejection.summary}"
                + (f" (문제로 고르지 않은 요소의 제약 {len(dropped)}개 제외)" if dropped else ""),
            }
        )
    elif decision["decision"] == "STALE":
        update.update(
            {**REVIEW_RESET, "selected_plan": None, "_detail": "승인 대기 중 원본이 바뀌어 최신 데이터로 다시 평가합니다"}
        )
    else:
        update["_detail"] = "필수 승인자 전원 승인"
    return update


@harnessed("commit_plan", "예약과 확정")
async def commit_plan(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """전원 승인된 변경안만 확정합니다. 데이터 버전이 바뀌었으면 확정하지 않고 재평가로 돌아갑니다."""
    approvals = state["approvals"]
    if approvals.get("decision") != "APPROVED":
        raise RuntimeError("승인되지 않은 변경안은 확정할 수 없습니다")
    try:
        result = await call_tool_or_raise(
            ctx,
            "business_commit_plan",
            {"proposal_id": approvals["proposal_id"], "data_version": state["data_version"]},
            approved=True,
        )
    except ToolCallError as error:
        if error.outcome.error_code == "VERSION_CONFLICT":
            return {"selected_plan": None, "callsheet_version_no": None, "_detail": "확정 직전 데이터 버전 충돌, 재평가합니다"}
        raise
    return {
        "callsheet_version_no": result["callsheetVersionNo"],
        "_detail": f"콜시트 v{result['callsheetVersionNo']} 확정, 예약 상태 {result['reservationStatus']}",
    }


@harnessed("publish", "공지와 알림")
async def publish(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """확정 결과를 완료 이벤트로 알립니다. 콜시트 배포와 알림 발송은 backend Outbox와 Worker가 맡습니다."""
    plan = state["selected_plan"]
    evidence = state.get("evidence") or {}
    cited = sorted({cid for item in plan["checklist"] for cid in item["evidenceIds"]})
    answer = (
        f"변경안 {state['approvals']['version_no']}이 전원 승인되어 확정되었습니다. "
        f"{describe(plan['candidate'])}. 콜시트 v{state['callsheet_version_no']} 배포를 요청했습니다."
    )
    result = {
        "answer": answer,
        "sources": [
            {"docId": evidence[c]["doc_id"], "title": evidence[c]["title"], "snippet": evidence[c]["text"][:160]} for c in cited
        ],
        "proposalId": state["approvals"]["proposal_id"],
        "callsheetVersionNo": state["callsheet_version_no"],
    }
    return {"result": result, "_detail": answer}


@harnessed("suggest_alternatives", "4안 구성")
async def suggest_alternatives(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """1/2/3안을 섞어도 실행 가능한 후보가 없거나 장소 문제로 거절되면, 세 안의 장소 특징과 씬 의도에서 키워드를 뽑아
    아워플레이스 대체 장소를 찾고, 4안 장소로 등록해 업무 규칙 엔진이 다시 평가하게 합니다."""
    plan_set = state["plan_set"]
    early = bool(state.get("widen_search"))
    situation = (
        "승인자가 장소를 문제 삼아 거절했습니다. 남은 1/2/3안 장소만으로는 거절 전보다 나은 안이 나올 수 없으니, "
        "거절 사유를 피하는 대체 장소를 찾아 후보를 넓힙니다."
        if early
        else "1/2/3안을 어떻게 섞어도 하드 제약과 거절 사유를 모두 만족하는 후보가 없습니다."
    )
    keywords = await ctx.model.structured(
        ctx,
        [
            SystemMessage(_system()),
            HumanMessage(
                render(
                    "alternative_keywords",
                    situation=situation,
                    plan_set=_json(plan_set["options"]),
                    scenes=_json(plan_set["block"]["scenes"]),
                    event=_json(state["event"]),
                    rejections="\n".join(state.get("loop_summaries") or []) or "없음",
                    extra=_json(state.get("extra_constraints") or []),
                )
            ),
        ],
        AlternativeKeywords,
    )
    found = await ctx.tools.call(
        ctx,
        "business_search_locations",
        {"keywords": keywords.keywords, "max_distance_km": keywords.max_distance_km},
        allowed=["business_search_locations"],
    )
    suggestions = (found.data or {}).get("locations", []) if found.ok else []
    registered = []
    if suggestions:
        # 검색 결과는 키워드가 많이 맞는 순이라 앞의 세 곳만 4안 후보로 올려 평가 범위를 좁힌다.
        chosen = [location["id"] for location in suggestions[:MAX_ALTERNATIVES]]
        outcome = await ctx.tools.call(
            ctx,
            "business_register_alternative_locations",
            {"shoot_day_id": state["shoot_day_id"], "external_location_ids": chosen, "keywords": keywords.keywords},
            allowed=["business_register_alternative_locations"],
        )
        registered = (outcome.data or {}).get("registered", []) if outcome.ok else []
    names = ", ".join(r["name"] for r in registered) or "없음"
    return {
        "alternatives_tried": True,
        "widen_search": False,
        "alternatives": registered,
        "suggestions": suggestions,
        "stop_condition": None if registered or early else NO_FEASIBLE_PLAN,
        "_detail": ("장소 거절로 후보를 넓힘, " if early else "")
        + f"키워드 {', '.join(keywords.keywords)}로 4안 장소 {len(registered)}곳 등록: {names}",
    }


@harnessed("report_human", "사람에게 보고")
async def report_human(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """멈춤 조건에 걸리면 지금까지의 최선안, 위반, 추천을 정리합니다. NEEDS_HUMAN 이벤트는 worker가 보냅니다."""
    stop = stop_condition(ctx.counter, ctx.settings.limits) or state.get("stop_condition") or NO_FEASIBLE_PLAN
    best = next(iter(state.get("candidates") or []), None)
    payload = {
        "reason": STOP_MESSAGES[stop],
        "stopCondition": stop,
        "best": {"summary": describe(best), "violations": best["violations"]} if best else None,
        "violations": state.get("violations") or [],
        "suggestions": state.get("suggestions") or [],
        "extraConstraints": state.get("extra_constraints") or [],
    }
    return {"stop_condition": stop, "result": payload, "_detail": payload["reason"]}
