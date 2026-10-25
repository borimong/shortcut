"""재계획 그래프의 노드입니다. 한 번의 루프는 최적안 하나만 냅니다."""

from __future__ import annotations

import json
import re
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
from app.josa import josa
from app.runtime import RunContext

# LLM이 고를 수 있는 도구 목록이다. 데이터를 바꾸는 도구는 넣지 않는다.
IMPACT_TOOLS = [
    "business_find_impacted_entities",
    "business_get_entity_context",
    "business_get_availability",
    "business_get_actor_schedule",
    "business_get_weather",
    "business_get_disaster_alerts",
]
CONSTRAINT_TOOLS = ["rag_search_regulation", "rag_search_contract_clause", "rag_search_script"]

MEMORY_NAMESPACE = ("shortcut", "rejections")
ISSUE_LABELS = {"LOCATION": "장소", "TIME": "시간대", "EQUIPMENT": "장비", "COST": "비용", "OTHER": "기타"}
# 문제 요소마다 만들 수 있는 제약 유형이다. 고르지 않은 요소를 건드리는 제약은 버린다.
ISSUE_CONSTRAINT_TYPES = {
    "LOCATION": {"EXCLUDE_LOCATION", "EXCLUDE_LOCATION_TIME", "REQUIRE_INDOOR", "REQUIRE_SETTING_MATCH"},
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


# 1/2/3안 시간대가 배우 일정으로 모두 막혀 엔진이 배우 가능 시간에 맞춰 만든 시간대의 안 번호다(PlanEngine.ADJUSTED_TIME_OPTION_NO).
ADJUSTED_TIME_OPTION_NO = 0


# 세트 고정 씬의 세트 장소가 1/2/3안 장소에 없어 엔진이 후보로 더한 장소의 안 번호다(PlanEngine.SET_LOCATION_OPTION_NO).
SET_LOCATION_OPTION_NO = 5


def _time_source(option_no: int) -> str:
    return "조정 시간, 1/2/3안 밖" if option_no == ADJUSTED_TIME_OPTION_NO else f"{option_no}안"


def _location_source(option_no: int) -> str:
    return "세트 장소, 1/2/3안 밖" if option_no == SET_LOCATION_OPTION_NO else f"{option_no}안"


def describe(candidate: dict[str, Any]) -> str:
    """후보안을 사람이 읽는 한 줄로 바꿉니다. 엔진이 씬 순서를 바꾼 후보는 새 씬 시각표를 붙입니다."""
    names = ", ".join(item["name"] for item in candidate["equipment"]["items"])
    text = (
        f"장소 {candidate['location']['name']}({_location_source(candidate['location']['optionNo'])}), "
        f"장비 {names}({candidate['equipment']['optionNo']}안), "
        f"시간 {candidate['time']['start']}~{candidate['time']['end']}({_time_source(candidate['time']['optionNo'])}), "
        f"종합 점수 {candidate['totalScore']}"
    )
    if candidate.get("sceneOrderChanged"):
        text += f", 씬 순서 변경 {scene_order_text(candidate)}"
    return text


def scene_order_text(candidate: dict[str, Any]) -> str:
    """씬 시각표를 "S19 14:00~14:30 → S18 14:30~16:00" 모양으로 씁니다."""
    return " → ".join(f"{s['code']} {s['start']}~{s['end']}" for s in candidate.get("sceneOrder") or [])


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
    # 장비 묶음 일부만 적으면 승인자가 빠진 장비를 안 가져가는 안으로 읽는다.
    left_out = missing_equipment(text, choice)
    if left_out:
        problems.append(f"설명에 제안 장비가 빠졌습니다: {', '.join(left_out)}")
    # 씬 순서가 바뀌면 배우 콜타임이 달라지므로 승인자가 새 순서를 설명에서 바로 볼 수 있어야 한다.
    codes = [s["code"] for s in choice.get("sceneOrder") or []]
    if choice.get("sceneOrderChanged") and not all(code in text for code in codes):
        problems.append(f"설명에 바뀐 씬 순서가 없습니다: {' → '.join(codes)}")
    # 순서는 그대로이고 시각만 옮긴 안을 "씬 순서를 바꿨다"고 쓰면 승인자가 콜시트 순서를 잘못 고친다.
    if not choice.get("sceneOrderChanged") and SCENE_ORDER_CLAIM.search(text):
        problems.append("설명에 바뀌지 않은 씬 순서를 바뀌었다고 썼습니다")
    return problems


# 대본 소프트 경고마다 승인 뒤 확인할 사람, 이미 적혀 있는지 볼 낱말, 넣을 미확정 항목이다.
# 엔진이 실행 가능하다고 본 후보라 위반은 아니고 사람 확인만 남는다.
SCRIPT_FOLLOW_UPS = {
    "SCRIPT_EXT_INDOOR": ("연출감독", "연출", "연출감독, 야외 장면을 실내에서 찍는 연출 확인, 승인 시"),
    "SCRIPT_INT_OUTDOOR": ("연출감독", "연출", "연출감독, 실내 장면을 야외에서 찍는 연출 확인, 승인 시"),
    "SCRIPT_EQUIPMENT_WANTED": ("촬영감독", "장비", "촬영감독, 대본상 있으면 좋은 장비 없이 찍는 방법 확인, 승인 시"),
}
SCENE_ORDER_FOLLOW_UP = "조감독, 바뀐 씬 순서로 배우 콜타임 다시 공지, 승인 즉시"
SHOOT_TIME_FOLLOW_UP = "조감독, 바뀐 촬영 시각으로 배우 콜타임 다시 공지, 승인 즉시"
# "씬 순서를 바꿔", "바뀐 씬 순서"처럼 순서가 바뀌었다고 쓴 말이다. "씬 순서는 그대로"는 걸리지 않는다.
SCENE_ORDER_CLAIM = re.compile(r"(바꾼|바뀐|바꿔|바뀌어|변경된|변경한) 씬 순서|씬 순서(를|가)? ?(바꾸|바꿨|바꿉|바꿔|바뀌|바뀝|바뀐|변경)")


def engine_warnings(candidate: dict[str, Any]) -> dict[str, list[str]]:
    """엔진 소프트 경고 문장을 하드 제약 범주별로 묶습니다."""
    warned: dict[str, list[str]] = {}
    for warning in candidate.get("warnings") or []:
        warned.setdefault(warning.get("constraint"), []).append(warning["message"])
    return warned


def missing_equipment(text: str, candidate: dict[str, Any]) -> list[str]:
    """설명에 나오지 않은 제안 장비 이름입니다."""
    return [item["name"] for item in candidate["equipment"]["items"] if item["name"] not in text]


def missing_cost_and_distance(text: str, candidate: dict[str, Any]) -> str:
    """설명에 이동 거리나 추가 비용 숫자가 빠졌으면 엔진 값으로 채울 한 문장을 만듭니다. 둘 다 있으면 빈 문자열입니다.
    검토에서 같은 지적이 되풀이되지 않도록 모델에게 맡기지 않고 코드가 붙입니다.
    "14.0km"와 "14km", "150,000원"과 "15만 원"처럼 표기가 달라도 같은 값이면 이미 있다고 봅니다."""
    km = f"{float(candidate['distanceKm']):g}"
    extra = int(candidate["extraCost"])
    amount = abs(extra)
    has_distance = any(
        abs(float(n) - float(candidate["distanceKm"])) < 0.05 for n in re.findall(r"(\d+(?:\.\d+)?)\s*km", text)
    )
    won = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)\s*원", text)]
    man = [round(float(n) * 10000) for n in re.findall(r"(\d+(?:\.\d+)?)\s*만\s*원?", text)]
    has_cost = "추가 비용" in text if extra == 0 else amount in won + man
    if extra > 0:
        cost = f"현재 확정안보다 {extra:,}원이 더 듭니다"
    elif extra < 0:
        cost = f"현재 확정안보다 {amount:,}원이 줄어듭니다"
    else:
        cost = "현재 확정안 대비 추가 비용은 없습니다"
    distance = f"목동 기준 이동 거리는 {km}km"
    if not has_distance and not has_cost:
        return f"{distance}이고, {cost}."
    if not has_distance:
        return f"{distance}입니다."
    if not has_cost:
        return f"{cost}."
    return ""


def shoot_time_changed(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """확정안과 촬영 시작이나 종료 시각이 다른지 봅니다. 백엔드는 "13:00:00", 후보는 "13:00"으로 줄 수 있어 앞 다섯 글자만 견줍니다."""
    if not current.get("start"):
        return False
    now = (str(current["start"])[:5], str(current.get("end") or "")[:5])
    return (candidate["time"]["start"][:5], candidate["time"]["end"][:5]) != now


def align_follow_ups(candidate: dict[str, Any], current: dict[str, Any], unresolved: list[str]) -> list[str]:
    """미확정 항목을 실제 변경에 맞춥니다. 순서가 그대로인데 "씬 순서"를 다시 공지하라는 항목은 빼고,
    엔진 경고와 씬 순서나 촬영 시각 변경에 따라 승인 뒤 사람이 할 일을 담당과 기한까지 채웁니다. 이미 적혀 있으면 넣지 않습니다."""
    reordered = bool(candidate.get("sceneOrderChanged"))
    items = [u for u in unresolved if reordered or "씬 순서" not in u]
    codes = [w.get("code") for w in candidate.get("warnings") or []]
    for code in dict.fromkeys(codes):
        if code not in SCRIPT_FOLLOW_UPS:
            continue
        owner, keyword, item = SCRIPT_FOLLOW_UPS[code]
        if not any(owner in u and keyword in u for u in items):
            items.append(item)
    if not any("콜타임" in u for u in items):
        if reordered:
            items.append(SCENE_ORDER_FOLLOW_UP)
        elif shoot_time_changed(candidate, current):
            items.append(SHOOT_TIME_FOLLOW_UP)
    return items


def to_mcp_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """엔진이 고른 씬 순서를 그대로 넘겨 검증 게이트와 변경안이 평가 때와 같은 순서를 판정하게 합니다."""
    body = {
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
    if candidate.get("sceneOrder"):
        body["scene_order"] = [s["code"] for s in candidate["sceneOrder"]]
    return body


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
        shoot_day_id=state["shoot_day_id"],
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
        scenes=", ".join(scene["code"] for scene in state["plan_set"]["block"]["scenes"]) or "없음",
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
        "location_blockers": result.get("locationProofBlockers") or [],
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
    warned = engine_warnings(choice)
    # 하드 제약 판정은 업무 규칙 엔진이 한다. 엔진이 고른 후보라 위반은 없으므로 상태도 엔진을 따른다.
    # 엔진 경고(대본 경고, 약한 비)가 있는 범주는 위반이 아니지만 승인자가 놓치지 않게 WARN으로 보이고, 자체 검토는 감점하지 않는다.
    # 엔진 경고가 없는 범주를 모델이 WARN으로 적으면(비행 금지 구역이 아닌 장소의 NO_FLY_ZONE 등) 없는 위험이라 PASS로 돌린다.
    # 근거 조각은 그대로 둔다. 근거가 없는 범주는 아래에서 다시 WARN이 된다.
    for constraint, item in checklist.items():
        if constraint in warned:
            item["status"] = "WARN"
            if not item["note"].strip():
                item["note"] = " ".join(warned[constraint])
        elif item["status"] == "WARN":
            item["status"] = "PASS"
            item["note"] = "업무 규칙 엔진 판정에서 위반과 경고가 없습니다"
    explanation = explained.explanation
    left_out = missing_equipment(explanation, choice)
    if left_out:
        # 다시 써도 장비 묶음 일부가 빠졌으면 승인자가 묶음 전체를 보도록 코드가 한 문장을 붙인다.
        names = ", ".join(item["name"] for item in choice["equipment"]["items"])
        explanation = f"{explanation.rstrip()} 장비 묶음은 {names}입니다."
    facts = missing_cost_and_distance(explanation, choice)
    if facts:
        explanation = f"{explanation.rstrip()} {facts}"
    problems = explanation_problems(explanation, choice, state["candidates"], current)
    unresolved = align_follow_ups(choice, current, list(explained.unresolved))
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
            "explanation": explanation,
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


def by_setting_fit(locations: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """대체 장소를 씬의 실내/실외에 맞는 곳부터 세운다. 같은 쪽 안에서는 검색 순서(키워드가 많이 맞는 순)를 지킨다.
    비나 재난 때문에 막혔으면 야외 장면이라도 실내가 먼저다. 밤 야외 장면이면 야경을 볼 수 있는 곳을 더 앞에 둔다."""
    scenes = state["plan_set"]["block"]["scenes"]
    exterior = any(scene.get("intExt") == "EXT" for scene in scenes)
    night = any(scene.get("timeOfDay") == "NIGHT" for scene in scenes)
    codes = {v["code"] for c in state.get("candidates") or [] for v in c.get("violations") or []}
    weather = state["event"].get("type") in {"RAIN", "DISASTER"} or bool(codes & {"RAIN_HARD", "DISASTER_ALERT"})
    want_indoor = weather or not exterior

    def rank(location: dict[str, Any]) -> tuple[int, int]:
        indoor = location.get("indoor")
        night_view = night and not want_indoor and any("야경" in k or "야간" in k for k in location.get("keywords") or [])
        return (0 if indoor is None or indoor == want_indoor else 1, 0 if night_view else 1)

    return sorted(locations, key=rank)


def review_facts(candidate: dict[str, Any]) -> str:
    """검토 모델이 비용이나 날씨를 잘못 읽고 감점하지 않도록 엔진이 확인한 값을 그대로 적습니다."""
    warnings = ", ".join(w["message"] for w in candidate.get("warnings") or []) or "없음"
    return (
        "하드 제약 위반: 0건 (업무 규칙 엔진과 검증 게이트가 계약, 일정, 법규, 예산 상한, 비행 금지, 재난, 날씨를 모두 확인함)\n"
        f"이 안의 장소와 장비 비용: {candidate['cost']}원 (블록 예산 상한 이내), 현재 확정안 대비 추가 비용: {candidate['extraCost']}원\n"
        f"목동 기준 이동 거리: {float(candidate['distanceKm']):g}km, 실내 여부: {'실내' if candidate['location']['indoor'] else '야외'}\n"
        f"엔진 경고(위반이 아니라 사람이 확인할 사항): {warnings}"
    )


@harnessed("self_review", "자체 검토")
async def self_review(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """승인 요청 전에 승인자 입장에서 안을 채점합니다. 통과 점수 미만이면 고쳐서 다시 검토하고,
    상한 회차에 닿거나 점수가 두 번 연속 그대로면 그때까지 가장 점수가 높았던 안으로 승인을 요청합니다."""
    limits = ctx.settings.limits
    plan = state["selected_plan"]
    candidate = plan["candidate"]
    round_no = state.get("review_round", 0) + 1
    warned = engine_warnings(candidate)

    def line(c: dict[str, Any]) -> str:
        text = f"{c['constraint']} {c['status']} 근거 {len(c['evidenceIds'])}건: {c['note']}"
        # 엔진 경고를 승인자에게 보이려고 둔 WARN이라 검토 모델이 위반 위험으로 읽고 감점하지 않게 밝혀 둔다.
        if c["status"] == "WARN" and c["evidenceIds"] and c["constraint"] in warned:
            text += " (엔진 경고를 승인자에게 보이려는 표시, 위반 아님, 감점하지 않음)"
        return text

    checklist = "\n".join(line(c) for c in plan["checklist"])
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
    passed = score >= limits.review_pass_score
    # 고쳐도 점수가 두 번 연속 그대로면 같은 지적이 되풀이되는 것이라 상한까지 돌지 않고 멈춘다.
    last_three = {h["score"] for h in history[-3:]}
    stalled = not passed and len(history) >= 3 and len(last_three) == 1
    if passed or stalled or round_no >= limits.max_review_rounds:
        chosen = plan if passed else best["plan"]
        final_score = score if passed else best["score"]
        if passed:
            outcome = "통과"
        elif stalled:
            outcome = f"점수가 두 번 연속 그대로라 멈추고 가장 높은 {best['round']}회차 {best['score']}점 안으로 승인 요청"
        else:
            outcome = f"{limits.max_review_rounds}회 도달, 가장 높은 {best['round']}회차 {best['score']}점 안으로 승인 요청"
        update.update(
            {
                "selected_plan": chosen,
                "review_next": "request_approval",
                "review_result": {
                    "score": final_score,
                    "passed": passed,
                    "stalled": stalled,
                    "threshold": limits.review_pass_score,
                    "rounds": round_no,
                    "chosenRound": round_no if passed else best["round"],
                    "history": history,
                },
                "_detail": f"{round_no}회차 {score}점, {outcome}",
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
        f"변경안 {josa(str(state['approvals']['version_no']), '이')} 전원 승인되어 확정되었습니다. "
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
    suggestions = by_setting_fit((found.data or {}).get("locations", []) if found.ok else [], state)
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
        + f"키워드 {josa(', '.join(keywords.keywords), '으로')} 4안 장소 {len(registered)}곳 등록: {names}",
    }


def closest_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """사람에게 보여 줄 가장 가까운 후보입니다. 되는 후보가 있으면 점수 1등을, 없으면 세트 고정에 걸리지 않은 후보 가운데
    위반이 가장 적은 것을 고릅니다. 점수 1등은 세트 밖 장소처럼 어떤 조율로도 성립하지 않는 안일 수 있습니다."""
    if not candidates:
        return None
    feasible = [c for c in candidates if c["feasible"]]
    if feasible:
        return feasible[0]

    def locked(candidate: dict[str, Any]) -> bool:
        return any(v["code"] == "SCRIPT_SETTING_LOCKED" for v in candidate["violations"])

    pool = [c for c in candidates if not locked(c)] or candidates
    return min(pool, key=lambda c: (len(c["violations"]), -c["totalScore"]))


@harnessed("report_human", "사람에게 보고")
async def report_human(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """멈춤 조건에 걸리면 지금까지의 최선안, 위반, 추천을 정리합니다. NEEDS_HUMAN 이벤트는 worker가 보냅니다."""
    stop = stop_condition(ctx.counter, ctx.settings.limits) or state.get("stop_condition") or NO_FEASIBLE_PLAN
    best = closest_candidate(state.get("candidates") or [])
    blockers = state.get("location_blockers") or []
    reason = STOP_MESSAGES[stop]
    if blockers:
        # 새 장소로는 풀리지 않으니 대체 장소를 권하지 않고, 무엇이 막는지 그대로 적어 사람이 일정이나 대본을 조정하게 한다.
        reason += ". 새 장소로는 풀 수 없는 원인: " + " ".join(blockers)
    payload = {
        "reason": reason,
        "stopCondition": stop,
        "best": {"summary": describe(best), "violations": best["violations"]} if best else None,
        "violations": state.get("violations") or [],
        "blockers": blockers,
        "suggestions": [] if blockers else state.get("suggestions") or [],
        "extraConstraints": state.get("extra_constraints") or [],
    }
    return {"stop_condition": stop, "result": payload, "_detail": payload["reason"]}
