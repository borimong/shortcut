"""재계획 그래프의 노드입니다. 한 번의 루프는 최적안 하나만 냅니다."""

from __future__ import annotations

import dataclasses
import difflib
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from app.graph.common import (
    ToolCallError,
    add_usage_to,
    call_tool_or_raise,
    feedback_block,
    harnessed,
    run_tool_loop,
    thought_of,
)
from app.graph.execution import AGENT_LABELS, AGENTS, DONE, build_execution_graph, execution_facts, latest_reports
from app.graph.schemas import (
    AlternativeKeywords,
    CandidateChoice,
    ConstraintSet,
    ImpactSummary,
    PlanExplanation,
    RejectionPlan,
    ReviewChecks,
    WeightAdjustment,
)
from app.graph.state import DEFAULT_WEIGHTS, HARD_CONSTRAINTS
from app.harness.context import Section, fit_sections, summarize_loops
from app.harness.instructions import render
from app.harness.limits import EXEC_NEEDS_HUMAN, NO_FEASIBLE_PLAN, STOP_MESSAGES, new_counter, stop_condition
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
    # 새 루프에서는 후보 장소가 바뀔 수 있으므로 근거를 다시 찾을 수 있게 한다.
    "evidence_stalled": False,
}
# 4안 후보로 올릴 대체 장소 수다. 많이 올리면 조합이 늘어 평가 결과가 길어지고 판단이 흐려진다.
MAX_ALTERNATIVES = 3
# 가중치가 한쪽으로 쏠리면 다른 기준이 사실상 무시되므로 각 가중치를 0.05~0.6 사이로 묶는다.
MIN_WEIGHT, MAX_WEIGHT = 0.05, 0.6
# 규정 검색을 실행하는 총 횟수 상한이다. 세 번 찾고도 근거가 없으면 미확정 항목으로 넘긴다.
MAX_INFO_RETRIES = 3
# 범주마다 근거가 될 수 있는 문서 종류다. 허가서는 장소별 허가 시간, 드론, 기상 조건, 사용료를 함께 담고 있어 여러 범주에 쓴다.
# 다른 종류의 조항을 인용하면(예: SCHEDULE에 근로기준법) 범주 근거로 세지 않는다.
EVIDENCE_TYPES = {
    "CONTRACT": {"CONTRACT"},
    "SCHEDULE": {"CONTRACT", "PERMIT"},
    "LAW": {"LAW", "PERMIT"},
    "BUDGET": {"POLICY", "PERMIT"},
    "NO_FLY_ZONE": {"NO_FLY", "PERMIT", "LAW"},
    "DISASTER": {"SAFETY", "PERMIT", "DATA"},
    "WEATHER": {"SAFETY", "PERMIT"},
}
# 문서 첫 제목 앞의 머리글 조각이다. 문서 소개일 뿐 조항이 아니므로 근거로 세지 않는다.
INTRO_HEADING = "개요"
# 업무 데이터 조회 결과를 근거로 쓸 때의 ID다. 문서 조항이 아니라 조회한 사실이라 원문 대조 없이 그대로 싣는다.
NO_DISASTER_ALERT_ID = "data:disaster_alerts"


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


def candidate_places(plan_set: dict[str, Any]) -> list[str]:
    """현재 확정안과 1/2/3안의 장소 이름을 중복 없이 모읍니다."""
    plans = [plan_set.get("current") or {}, *(plan_set.get("options") or [])]
    names = [(plan.get("location") or {}).get("name") for plan in plans]
    return list(dict.fromkeys(name for name in names if name))


def applies_to_places(hit: dict[str, Any], places: list[str]) -> bool:
    """조항에 적용 장소가 붙어 있으면 후보 장소 이름 가운데 하나에 그 키워드가 들어 있어야 합니다.
    적용 장소가 없는 조항(법령, 사내 규정)이나 후보 장소를 모르는 경우는 그대로 둡니다."""
    keywords = [k.replace(" ", "") for k in hit.get("locations") or []]
    if not keywords or not places:
        return True
    names = [p.replace(" ", "") for p in places]
    return any(k in name for k in keywords for name in names)


# 장소마다 따로 내주는 문서라 다른 장소의 안에는 근거가 될 수 없는 종류다.
# 비행금지 안내는 피해야 할 장소 목록이라 목록에 없는 장소의 안에도 근거가 되므로 넣지 않는다.
PLACE_BOUND_TYPES = {"PERMIT"}


def usable_for_place(hit: dict[str, Any], place: str) -> bool:
    """고른 안의 장소에서 근거로 쓸 수 있는 조항인지 봅니다. 성수 안의 허가 시간 근거로 한강 허가서를 쓰지 않게 한다."""
    return hit.get("doc_type") not in PLACE_BOUND_TYPES or applies_to_places(hit, [place])


def data_evidence(conditions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """재난 문자가 한 건도 없다는 조회 결과를 DISASTER 범주의 근거로 만듭니다.
    재난 문자 조항은 '발령되면 그 지역 촬영을 하지 않는다'는 조건이라, 조항만으로는 이번 촬영이 괜찮은지 알 수 없고
    발령이 없다는 사실이 있어야 통과로 판단할 수 있다. 발령된 문자가 있으면 만들지 않고 조항 근거로만 판단한다."""
    alerts = (conditions.get("disaster_alerts") or {}).get("alerts")
    if alerts is None or alerts:
        return {}
    return {
        NO_DISASTER_ALERT_ID: {
            "chunk_id": NO_DISASTER_ALERT_ID,
            "doc_id": "business:disaster_alerts",
            "doc_type": "DATA",
            "title": "업무 데이터 조회 결과",
            "heading": "재난 문자",
            "text": "촬영일 촬영 지역에 발령된 재난 문자가 없습니다(재난 문자 조회 결과 0건).",
        }
    }


def counts_as_evidence(constraint: str, hit: dict[str, Any]) -> bool:
    return hit.get("heading") != INTRO_HEADING and hit.get("doc_type") in EVIDENCE_TYPES.get(constraint, set())


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
    ) + feedback_block(state)
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
                + feedback_block(state)
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
        "_thought": thought_of(
            summary,
            {
                "observation": f"영향 엔티티 {len(summary.impacted)}개, 위험: {'; '.join(summary.risks) or '없음'}",
                "decision": "이 범위로 하드 제약 근거를 모읍니다",
                "reason": "온톨로지, 날씨, 재난 문자, 가용 자원 조회 결과를 묶었습니다",
            },
        ),
        "_revisable": True,
    }


@harnessed("collect_constraints", "제약 수집")
async def collect_constraints(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """모델이 규정 검색 도구를 골라 하드 제약 범주별 원문 근거를 모읍니다."""
    impacted = state["impacted_entities"]
    places = candidate_places(state.get("plan_set") or {})
    contracts = set(impacted["contract_doc_ids"])
    user = render(
        "constraint_collection",
        event=_json(state["event"]),
        contracts=", ".join(impacted["contract_doc_ids"]),
        places=", ".join(places) or "알 수 없음",
        risks="\n".join(impacted["risks"]) or "없음",
        alerts=_json(state["conditions"]["disaster_alerts"]),
        missing=", ".join(state.get("missing_info") or []) or "없음",
    ) + feedback_block(state)
    outcomes, _ = await run_tool_loop(ctx, _system(), user, CONSTRAINT_TOOLS, ctx.settings.limits.max_node_tool_rounds)

    evidence = dict(state.get("evidence") or {})
    excluded = set()
    for outcome in outcomes:
        if outcome.ok:
            for hit in outcome.data:
                # 다른 장소의 허가서나 비행 금지 구역, 대상이 아닌 배우의 계약서는 이번 재계획의 근거가 아니다.
                # 정리 단계에 넘기면 범주 이름만 보고 인용하는 경우가 있어 여기서 뺀다.
                if not applies_to_places(hit, places) or (hit["doc_type"] == "CONTRACT" and hit["doc_id"] not in contracts):
                    excluded.add(hit["chunk_id"])
                    continue
                evidence[hit["chunk_id"]] = hit
    facts = data_evidence(state["conditions"])
    evidence.update(facts)

    found = await ctx.model.structured(
        ctx,
        [
            SystemMessage(_system()),
            HumanMessage(
                render("constraint_summary", places=", ".join(places) or "알 수 없음", evidence=_evidence_lines(evidence))
                + feedback_block(state)
            ),
        ],
        ConstraintSet,
    )
    findings: dict[str, dict[str, Any]] = {}
    for finding in found.findings:
        # 모델이 검색하지 않은 ID를 근거로 적으면 확인할 수 없으므로 실제로 받은 chunk_id만 남긴다.
        # 범주와 맞지 않는 종류의 문서를 적은 것도 그 범주의 근거로 세지 않는다.
        cited = [cid for cid in finding.evidence_ids if cid in evidence and counts_as_evidence(finding.constraint, evidence[cid])]
        findings[finding.constraint] = {"constraint": finding.constraint, "summary": finding.summary, "evidence_ids": cited}
    # 다시 수집할 때 모델이 이전에 인용한 근거를 빠뜨려도 지우지 않는다. 재수집은 빈 범주를 채우려는 것인데,
    # 정리를 처음부터 다시 받으면 앞에서 찾은 날씨 근거가 빠져 빈 범주가 오히려 늘어난 적이 있다.
    previous = state.get("hard_constraints") or []
    for before in previous:
        item = findings.setdefault(before["constraint"], {"constraint": before["constraint"], "summary": "", "evidence_ids": []})
        if not item["evidence_ids"]:
            item["summary"] = before["summary"]
        item["evidence_ids"] = [
            *before["evidence_ids"],
            *(cid for cid in item["evidence_ids"] if cid not in before["evidence_ids"]),
        ]
    if NO_DISASTER_ALERT_ID in facts:
        # 발령이 없다는 사실은 조회로 확정됐으므로 모델이 인용을 빠뜨려도 코드가 붙인다.
        disaster = findings.setdefault(
            "DISASTER", {"constraint": "DISASTER", "summary": facts[NO_DISASTER_ALERT_ID]["text"], "evidence_ids": []}
        )
        if NO_DISASTER_ALERT_ID not in disaster["evidence_ids"]:
            disaster["evidence_ids"].append(NO_DISASTER_ALERT_ID)
    rechecked = await recheck_empty_categories(ctx, state, findings, evidence)

    covered = {c for c, f in findings.items() if f["evidence_ids"]}
    missing = [c for c in HARD_CONSTRAINTS if c not in covered]
    # 다시 찾았는데 새 조항도 새로 채운 범주도 없으면 더 찾아도 같은 결과라 재수집을 멈추게 한다.
    previous_covered = {f["constraint"] for f in previous if f["evidence_ids"]}
    stalled = bool(previous) and not set(evidence) - set(state.get("evidence") or {}) and covered <= previous_covered
    return {
        "evidence": evidence,
        "hard_constraints": [findings[c] for c in HARD_CONSTRAINTS if c in findings],
        "missing_info": missing,
        "evidence_stalled": stalled,
        "info_retries": state.get("info_retries", 0) + 1,
        "_detail": f"근거 {len(evidence)}건, 대상 밖 조항 {len(excluded)}건 제외, "
        + (f"빈 범주 재확인으로 {', '.join(rechecked)} 채움, " if rechecked else "")
        + f"근거 부족 범주 {', '.join(missing) or '없음'}"
        + (", 새로 찾은 근거가 없어 재수집을 멈춤" if stalled else ""),
        "_thought": thought_of(
            found,
            {
                "observation": f"근거 조항 {len(evidence)}건, 대상 밖 조항 {len(excluded)}건 제외",
                "decision": f"근거 부족 범주: {', '.join(missing) or '없음'}",
                "reason": "범주마다 맞는 문서 종류와 후보 장소에 적용되는 조항만 근거로 셉니다",
            },
        ),
        "_revisable": True,
    }


async def recheck_empty_categories(
    ctx: RunContext,
    state: dict[str, Any],
    findings: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    only: set[str] | None = None,
) -> list[str]:
    """정리에서 빈 범주를, 그 범주에 맞는 종류의 조항만 추려 한 번 더 묻습니다. 채운 범주를 돌려줍니다.
    조항 20여 건이 섞인 목록에서는 모델이 맞는 조항(재난 문자 원칙 등)을 받아 두고도 범주를 비워 두는 일이 잦았다.
    다시 검색하는 것보다 이미 받은 조항에서 고르게 하는 편이 빠르고, 고를 조항이 없으면 모델을 부르지 않는다."""
    options: dict[str, list[str]] = {}
    for constraint in HARD_CONSTRAINTS:
        if (findings.get(constraint) or {}).get("evidence_ids") or (only is not None and constraint not in only):
            continue
        ids = [cid for cid, hit in evidence.items() if counts_as_evidence(constraint, hit)]
        if ids:
            options[constraint] = ids
    if not options:
        return []
    sections = "\n\n".join(
        f"## {constraint}\n" + _evidence_lines({cid: evidence[cid] for cid in ids}) for constraint, ids in options.items()
    )
    answer = await ctx.model.structured(
        ctx,
        [
            SystemMessage(_system()),
            HumanMessage(render("constraint_recheck", event=_json(state["event"]), sections=sections) + feedback_block(state)),
        ],
        ConstraintSet,
    )
    filled = []
    for finding in answer.findings:
        picked = {finding.constraint: [cid for cid in finding.evidence_ids if cid in options.get(finding.constraint, [])]}
        summary = finding.summary
        if not picked[finding.constraint]:
            # 재난 문자가 걸린 사건에서 일정 칸의 계약 조항을 고르고 범주 이름은 DISASTER로 적은 일이 있었다.
            # 고른 조항이 어느 범주의 후보인지는 코드가 아니까, 한 범주의 후보에만 있는 조항은 그 범주로 넣는다.
            # 요약은 틀린 범주를 보고 쓴 것이라 조항 제목으로 바꾼다.
            picked = {}
            for cid in finding.evidence_ids:
                owners = [c for c, ids in options.items() if cid in ids]
                if len(owners) == 1:
                    picked.setdefault(owners[0], []).append(cid)
            summary = ""
        for constraint, cited in picked.items():
            if cited and constraint not in filled:
                headings = ", ".join(evidence[cid]["heading"] for cid in cited)
                findings[constraint] = {
                    "constraint": constraint,
                    "summary": summary or f"{headings} 조항을 적용합니다",
                    "evidence_ids": cited,
                }
                filled.append(constraint)
    return filled


async def constraints_for_place(
    ctx: RunContext, state: dict[str, Any], place: str, evidence: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """제약 정리 결과에서 고른 장소에 쓸 수 없는 근거를 빼고, 그 때문에 빈 범주는 이 장소에 맞는 조항에서 다시 고릅니다.
    성수 안의 일정 근거가 한강 허가서뿐이었다면 배우 계약서의 가용 시간 조항으로 바꾼다.
    같은 수집 결과와 같은 장소로 여러 번 구성하므로 결과를 State에 두고 다시 쓴다."""
    cached = (state.get("place_constraints") or {}).get(place)
    if cached and cached["info_retries"] == state.get("info_retries", 0):
        return cached["hard"]
    findings = {}
    lost = set()
    for h in state.get("hard_constraints") or []:
        kept = [cid for cid in h["evidence_ids"] if cid in evidence]
        if h["evidence_ids"] and not kept:
            lost.add(h["constraint"])
        findings[h["constraint"]] = {**h, "evidence_ids": kept}
    if lost:
        await recheck_empty_categories(ctx, state, findings, evidence, only=lost)
    return [findings[c] for c in HARD_CONSTRAINTS if c in findings]


@harnessed("reevaluate_plans", "1/2/3안 재평가")
async def reevaluate_plans(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """감독 지시가 있으면 가중치를 조정하고, 업무 규칙 엔진으로 27개 조합을 다시 평가합니다."""
    weights = dict(state.get("weights") or DEFAULT_WEIGHTS)
    rationale = state.get("weight_rationale", "")
    instruction = (state["event"].get("instruction") or "").strip()
    feedback = state.get("user_feedback") or []
    # 사용자 수정 요청이 새로 들어오면 이미 조정한 가중치라도 요청을 반영해 다시 조정한다.
    new_feedback = len(feedback) > state.get("weights_feedback_count", 0)
    thought = None
    if (instruction and not rationale) or new_feedback:
        adjusted = await ctx.model.structured(
            ctx,
            [
                SystemMessage(_system()),
                HumanMessage(
                    render("weight_adjust", instruction=instruction or "없음", weights=_json(weights)) + feedback_block(state)
                ),
            ],
            WeightAdjustment,
        )
        thought = thought_of(
            adjusted,
            {
                "observation": f"감독 지시: {instruction or '없음'}",
                "decision": "가중치를 다시 정했습니다",
                "reason": adjusted.rationale,
            },
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
        "weights_feedback_count": len(feedback),
        "_detail": detail,
        "_thought": thought,
        "_revisable": True,
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
    chose_thought = None
    if choice is not None and state.get("user_feedback"):
        # 사용자 수정 요청이 있을 때만 엔진 상위 5개 가운데 LLM이 고를 수 있다. 실행 가능 여부는 엔진이 이미 판정했고,
        # 고른 안도 검증 게이트를 다시 거친다.
        top = feasible[:5]
        picked = await ctx.model.structured(
            ctx,
            [
                SystemMessage(_system()),
                HumanMessage(
                    render(
                        "candidate_choice",
                        default=f"{choice['hash']} / {describe(choice)}",
                        candidates="\n".join(f"{c['hash']} / {describe(c)} / 추가 비용 {c['extraCost']}원" for c in top),
                    )
                    + feedback_block(state)
                ),
            ],
            CandidateChoice,
        )
        chosen = next((c for c in top if c["hash"] == picked.chosen_hash), None)
        if chosen is not None:
            choice = chosen
            chose_thought = thought_of(
                picked,
                {
                    "observation": f"실행 가능 상위 후보 {len(top)}개",
                    "decision": describe(chosen),
                    "reason": "사용자 수정 요청에 가장 맞는 후보로 바꿨습니다",
                },
            )
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

    # 고른 안의 장소에 맞는 조항만 보여 주고 근거로 센다. 제약 수집은 후보 장소 전체로 거르므로 현재 장소(한강)의 허가서가
    # 남아 있어, 성수 안의 허가 시간 근거로 한강 허가서를 인용한 일이 있었다.
    place = choice["location"]["name"]
    evidence = {cid: hit for cid, hit in (state.get("evidence") or {}).items() if usable_for_place(hit, place)}
    hard = await constraints_for_place(ctx, state, place, evidence)
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
        Section("직전 거절", _rejection_line(state.get("last_rejection")), 0),
        Section("자체 검토 피드백 (반드시 반영)", "\n".join(state.get("review_feedback") or []) or "없음", 0),
        Section("사용자 수정 요청 (반드시 반영)", "\n".join(state.get("user_feedback") or []) or "없음", 0),
        Section("하드 제약과 근거 요약", _json(hard), 1),
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
        # 제약 수집과 같은 기준으로 센다. 범주와 맞지 않는 종류의 문서, 문서 머리말(개요), 조회 결과를 다른 범주에 쓴 것은 빠진다.
        cited = [cid for cid in entry.evidence_ids if cid in evidence and counts_as_evidence(entry.constraint, evidence[cid])]
        checklist[entry.constraint] = {
            "constraint": entry.constraint,
            "status": entry.status,
            "note": entry.note,
            "evidenceIds": cited,
        }
    if NO_DISASTER_ALERT_ID in evidence:
        # 재난 문자가 없다는 조회 결과가 있으면 DISASTER는 통과다. 모델이 근거 없이 경고로 적어도 조회 사실로 바로잡는다.
        item = checklist.get("DISASTER") or {"constraint": "DISASTER", "note": "", "evidenceIds": []}
        checklist["DISASTER"] = {
            **item,
            "status": "PASS",
            "note": item["note"] or "촬영 지역에 발령된 재난 문자가 없습니다",
            "evidenceIds": [
                *item["evidenceIds"],
                *([] if NO_DISASTER_ALERT_ID in item["evidenceIds"] else [NO_DISASTER_ALERT_ID]),
            ],
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
            # 자체 검토가 '이미 찾은 근거를 인용하라'고 할 때도 이 장소에 맞는 근거만 권하게 같이 넘긴다.
            "hard_constraints": hard,
        },
        "place_constraints": {
            **(state.get("place_constraints") or {}),
            place: {"info_retries": state.get("info_retries", 0), "hard": hard},
        },
        "missing_info": missing,
        "repeat_filtered": False,
        "_detail": describe(choice) + (f" (거절된 안과 겹치는 후보 {len(repeats)}개 제외)" if repeats else ""),
        # 사용자 요청으로 후보를 바꿨으면 그 판단을, 아니면 설명을 쓴 판단을 생각 기록에 남긴다.
        "_thought": chose_thought
        or thought_of(
            explained,
            {"observation": describe(choice), "decision": "이 후보로 변경안을 씁니다", "reason": explained.explanation[:200]},
        ),
        "_revisable": True,
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


# 자체 검토 항목마다 20점이다. 셀 수 있는 항목은 코드가 계산하고, 글을 읽어야 하는 항목만 모델의 점검 답을 쓴다.
REVIEW_ITEM_MAX = 20
# compose_plan이 스스로 붙이는 미확정 항목이다. 근거 점수와 사실 대조에서 이미 깎으므로 담당과 기한 점검에서 뺀다.
SYSTEM_UNRESOLVED = ("근거 조항 확인 필요", "설명 확인 필요")
NUMBER_KINDS = {
    "시간": re.compile(r"\d{1,2}:\d{2}|\d{1,2}\s*시"),
    "비용": re.compile(r"\d[\d,]*\s*원|\d+\s*만\s*원"),
    "거리": re.compile(r"\d+(?:\.\d+)?\s*km"),
    "강수량": re.compile(r"\d+(?:\.\d+)?\s*mm|강수\s*확률\s*\d+\s*%"),
}
# 미확정 항목의 담당과 기한은 표현이 정해져 있어 코드로 찾는다. 모델은 통보 대상을 담당으로 옮기는 경우가 있었다.
OWNER = re.compile(r"제작실장|제작부|제작\s*PD|연출|조감독|감독|촬영팀|조명팀|동시녹음|녹음팀|미술팀|팀장|실장|매니저|담당")
DEADLINE = re.compile(r"\d{1,2}\s*시|\d{1,2}:\d{2}|즉시|직후|이내|까지|\d+\s*(분|시간)\s*안|오늘|내일|당일|전날|\d+일")
COST_WORDS = re.compile(r"비용|원|료|예산|금액|대여|대관")
# 비용 이유는 금액을 다시 적은 문장이 아니라 원인을 밝힌 문장이어야 한다. 모델은 금액 문장을 이유로 인용하는 경우가 있었다.
COST_CAUSE = re.compile(r"때문|위해|인해|이유|원인|대관료|대여료|사용료|임대료|료가|료이|료로|붙")
# 현재 확정안에서 빠지는 장비를 언급할 때 붙는 표현이다. 없으면 그 장비를 계속 쓴다고 읽힌다.
REMOVAL = re.compile(r"제외|빼|뺐|대신|없이|제거|교체|바꾸|바꿨|반납|취소")
NO_EXTRA_COST = re.compile(r"추가\s*비용(이|은)?\s*없|추가\s*비용\s*0\s*원|비용(은|이)?\s*(현재\s*확정안과\s*)?같")


def evidence_score(checklist: list[dict[str, Any]]) -> tuple[int, list[str], list[str]]:
    """WARN 하나에 2점, 근거 0건 범주 하나에 4점을 빼고, 근거 0건 범주가 있으면 12점을 넘지 않게 합니다."""
    by_constraint = {c["constraint"]: c for c in checklist}
    empty = [c for c in HARD_CONSTRAINTS if not (by_constraint.get(c) or {}).get("evidenceIds")]
    warns = [c for c in HARD_CONSTRAINTS if c not in empty and by_constraint[c]["status"] == "WARN"]
    score = max(REVIEW_ITEM_MAX - 2 * len(warns) - 4 * len(empty), 0)
    return (min(score, 12) if empty else score), warns, empty


def number_kinds(text: str) -> list[str]:
    return [kind for kind, pattern in NUMBER_KINDS.items() if pattern.search(text)]


def fact_problems(text: str, choice: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """설명의 장소와 장비 이름, 금액, 거리, 시각이 엔진이 준 값과 맞는지 봅니다.
    비교 후보와 현재 확정안의 값은 비교 설명에 쓸 수 있으므로 허용합니다."""
    plan_set = state.get("plan_set") or {}
    current = plan_set.get("current") or {}
    candidates = state["candidates"]
    options = plan_set.get("options") or []
    # 거절된 장소와, 사람이 거절 사유나 사건 내용에 직접 적은 장소와 장비 이름은 그 사유를 설명하는 데 필요하므로 이름 검사에서 뺀다.
    named = text
    rejections = [state.get("last_rejection") or {}, *(state.get("rejected_plans") or [])]
    # 거절된 장소는 거절 뒤 후보에서 빠지므로 1/2/3안과 현재 확정안에서도 이름을 찾는다.
    locations = [
        *(c["location"] for c in candidates),
        *((o.get("location") or {}) for o in options),
        current.get("location") or {},
    ]
    names = {loc.get("id"): loc.get("name", "") for loc in locations}
    context = " ".join([state["event"].get("detail") or "", *(r.get("reason", "") for r in rejections)])
    every = {loc.get("name", "") for loc in locations} | {i["name"] for c in candidates for i in c["equipment"]["items"]}
    allowed = {names.get(r.get("location_id"), "") for r in rejections} | {n for n in every if n and n in context}
    for part in sorted(allowed - {""}, key=len, reverse=True):
        named = named.replace(part, " ")
    if choice["location"]["name"] in text:
        named += f" {choice['location']['name']}"
    problems = explanation_problems(named, choice, candidates, current)
    chosen = {item["name"] for item in choice["equipment"]["items"]}
    dropped = {item.get("name") for item in current.get("equipment") or []} - chosen - {None, ""}
    # 사건이나 거절 사유에 나온 장비(예: 고장 난 반사판)는 그 문제를 설명하느라 언급하므로 뺀다.
    dropped = {name for name in dropped if name not in context}
    for sentence in re.split(r"(?<=[.다])\s+", text):
        named_here = sorted(name for name in dropped if name in sentence)
        if named_here and not REMOVAL.search(sentence):
            problems.append(f"현재 확정안에서 빠지는 장비를 쓴다고 적었습니다: {', '.join(named_here)}")
    amounts = {abs(v) for c in candidates for v in (c["cost"], c["extraCost"], c["cost"] - c["extraCost"])}
    amounts |= {current.get("cost"), *((o.get("location") or {}).get("cost") for o in options)}
    for raw in re.findall(r"(\d[\d,]*)\s*원", text):
        if int(raw.replace(",", "")) not in amounts:
            problems.append(f"엔진 값에 없는 금액이 있습니다: {raw}원")
    for raw in re.findall(r"(\d+)\s*만\s*원", text):
        if int(raw) * 10000 not in amounts:
            problems.append(f"엔진 값에 없는 금액이 있습니다: {raw}만 원")
    distances = {c["distanceKm"] for c in candidates}
    distances |= {
        (current.get("location") or {}).get("distanceKm"),
        *((o.get("location") or {}).get("distanceKm") for o in options),
    }
    for raw in re.findall(r"(\d+(?:\.\d+)?)\s*km", text):
        if float(raw) not in distances:
            problems.append(f"엔진 값에 없는 거리가 있습니다: {raw}km")
    times = {c["time"][k] for c in candidates for k in ("start", "end")}
    times |= {current.get("start"), current.get("end"), *(o.get(k) for o in options for k in ("start", "end"))}
    times |= set(re.findall(r"\d{1,2}:\d{2}", state["event"].get("detail") or ""))
    for raw in re.findall(r"\d{1,2}:\d{2}", text):
        if raw not in times:
            problems.append(f"후보와 사건에 없는 시각이 있습니다: {raw}")
    if choice["extraCost"] > 0 and NO_EXTRA_COST.search(text):
        problems.append(f"추가 비용이 {choice['extraCost']:,}원인데 추가 비용이 없다고 적었습니다")
    return problems


def _squash(text: str) -> str:
    return re.sub(r"[\s'\"“”‘’.,()]", "", text)


def quoted(check: Any, text: str, *must: re.Pattern) -> bool:
    """모델이 그렇다고 답해도 근거 구절이 설명에 없으면 아니오로 봅니다. 글을 읽지 않고 답하는 것을 막는다.
    must를 주면 인용에 그 표현이 모두 있어야 합니다. 질문과 상관없는 문장을 인용하는 경우를 거른다."""
    if not check.found or not all(pattern.search(check.quote) for pattern in must):
        return False
    quote, body = _squash(check.quote), _squash(text)
    if len(quote) < 4:
        return False
    if quote in body:
        return True
    # 모델이 조사나 어미를 조금 바꿔 옮기는 경우가 있어 가장 긴 공통 구간이 인용의 80% 이상이면 인정한다.
    match = difflib.SequenceMatcher(None, quote, body).find_longest_match(0, len(quote), 0, len(body))
    return match.size >= 0.8 * len(quote)


def review_questions(plan: dict[str, Any], state: dict[str, Any]) -> str:
    """상황에 맞는 질문만 적습니다. 조건이 붙은 질문을 하나로 묶으면 모델이 엉뚱한 쪽으로 답하는 경우가 있었다."""
    candidate = plan["candidate"]
    rejection = state.get("last_rejection")
    skip = "해당 없음. found를 false로 둡니다."
    lines = [
        "- change: 설명이 무엇이 바뀌었는지(장소, 장비, 시간 중 바뀐 것)를 적었는가",
        "- reason: 설명이 왜 이 조합을 골랐는지 구체적인 이유를 적었는가. 무슨 일(비, 소음, 재난, 장비 고장 등)이 생겼고 이 조합이 그것을"
        " 어떻게 피하는지가 함께 있어야 합니다. '상황 변화에 맞춰', '여러 요소를 고려해' 같은 일반적인 말은 이유가 아닙니다.",
    ]
    if rejection:
        issues = ", ".join(ISSUE_LABELS.get(i, i) for i in rejection.get("issues") or []) or "문제 요소"
        lines.append(
            f"- responds: 설명이 직전 거절 사유('{rejection.get('reason', '')}')를 직접 언급했는가. "
            "'의견을 반영했다'처럼 무슨 사유인지 밝히지 않은 말은 false입니다."
        )
        lines.append(f"- rejected_element: 설명이 직전 거절에서 지목된 {issues}를 무엇으로 바꿨는지 적었는가")
    else:
        detail = state["event"].get("detail") or ""
        lines.append(f"- responds: 설명이 변경 이벤트('{detail}')에서 무슨 일이 생겼는지를 언급했는가")
        lines.append(f"- rejected_element: {skip}")
    if candidate["extraCost"] > 0:
        lines.append(
            f"- cost_reason: 설명이 추가 비용 {candidate['extraCost']:,}원이 무엇 때문에 드는지(대관료, 장비 대여료처럼 비용의 원인)를 적었는가. "
            "'문제없다', '예산 상한 안이다'는 원인이 아닙니다."
        )
    else:
        lines.append(f"- cost_reason: {skip}")
    return "\n".join(lines)


# 사건 문장에서 대응 여부를 가르는 데 쓰지 않는 낱말이다.
GENERIC_WORDS = {"이후", "이전", "오전", "오후", "예보", "너무", "모두", "갑자기", "그리고", "있는", "없는", "발생"}


def key_words(text: str, state: dict[str, Any]) -> list[str]:
    """사건이나 거절 사유의 낱말 중 장소 이름과 흔한 말을 뺀 것입니다. 설명이 그 일을 언급했는지 볼 때 씁니다."""
    plan_set = state.get("plan_set") or {}
    places = [c["location"]["name"] for c in state["candidates"]]
    places += [
        (o.get("location") or {}).get("name", "") for o in [*(plan_set.get("options") or []), plan_set.get("current") or {}]
    ]
    place_words = {w for name in places for w in name.split()}
    words = re.findall(r"[가-힣A-Za-z]{2,}|\d+\s*(?:시|mm|%)", text)
    return [w for w in words if w not in place_words and w not in GENERIC_WORDS]


def mentions(check: Any, text: str, source: str, state: dict[str, Any]) -> bool:
    """설명이 사건이나 거절 사유(source)를 언급했는지 봅니다. 인용이 설명에 있으면 인용에 source 낱말이 있어야 하고,
    모델이 설명 대신 source 문장을 그대로 베껴 온 경우에는 설명 전체에 source 낱말이 있는지 코드가 직접 확인합니다."""
    words = key_words(source, state)
    if not check.found:
        return False
    if quoted(check, text):
        return not words or any(w in check.quote for w in words)
    copied = len(_squash(check.quote)) >= 4 and _squash(check.quote) in _squash(source)
    return copied and any(w in text for w in words)


def score_review(checks: ReviewChecks, plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """점검 답과 코드 검사로 항목 점수, 통과를 막는 사유, 고칠 점을 만듭니다."""
    candidate = plan["candidate"]
    text = plan["explanation"]
    rejection = state.get("last_rejection")
    feedback: list[str] = []
    blocking: list[str] = []

    evidence, warns, empty = evidence_score(plan["checklist"])
    # 제약 수집이 이미 찾은 근거가 있는데 설명 단계에서 인용만 빠진 범주는 다시 검색하지 않고 그 ID를 인용하게 한다.
    # 다시 검색하면 같은 근거를 또 찾느라 도구 호출만 늘어 루프 한도에 걸린 적이 있다.
    # 고른 안의 장소에 맞게 추린 근거(compose_plan이 만든 것)를 쓴다. 성수 안에 한강 허가서를 인용하라고 하지 않는다.
    hard = plan.get("hard_constraints") or state.get("hard_constraints") or []
    found = {h["constraint"]: h.get("evidence_ids") or [] for h in hard}
    citable = {c: found[c][:2] for c in empty if found.get(c)}
    if empty:
        blocking.append("근거 0건 범주")
    if citable:
        feedback.append(
            "체크리스트에 근거 ID가 빠진 범주가 있습니다. 이미 찾은 근거를 인용하세요: "
            + ", ".join(f"{c} {' '.join(ids)}" for c, ids in citable.items())
        )
    if set(empty) - set(citable):
        missing = [c for c in empty if c not in citable]
        feedback.append(f"{', '.join(missing)} 범주에 근거 조항이 없습니다. 규정을 더 찾아 근거를 붙이세요.")
    if warns:
        feedback.append(
            f"{', '.join(warns)} 범주가 WARN입니다. 근거 조항으로 확인되면 PASS로, 아니면 미확정 항목에 담당과 기한을 적으세요."
        )

    facts = fact_problems(text, candidate, state)
    if facts:
        explanation = 0
        blocking.append("설명의 사실 오류")
        feedback.append(f"설명이 엔진 값과 다릅니다: {'; '.join(facts)}. 엔진 값 그대로 고치세요.")
    else:
        kinds = number_kinds(text)
        explanation = (6 if quoted(checks.change, text) else 0) + (7 if quoted(checks.reason, text) else 0)
        explanation += 7 if len(kinds) >= 2 else 3 if kinds else 0
        if not quoted(checks.change, text):
            feedback.append(
                f"무엇이 바뀌었는지(장소, 장비, 시간)를 설명에 적으세요. 선택한 장소는 {candidate['location']['name']}입니다."
            )
        if not quoted(checks.reason, text):
            feedback.append("왜 이 조합인지 변경 이벤트와 연결한 이유를 적으세요.")
        if len(kinds) < 2:
            feedback.append("시간, 비용, 거리, 강수량 중 숫자를 두 가지 이상 적으세요.")

    # '의견을 반영했다'처럼 사유를 밝히지 않은 문장은 사유의 낱말이 없어 걸러진다.
    source = (rejection.get("reason") or "") if rejection else (state["event"].get("detail") or "")
    responds = mentions(checks.responds, text, source, state)
    if rejection:
        element = quoted(checks.rejected_element, text)
        answered = (12 if responds else 0) + (8 if element else 0)
        if not responds:
            blocking.append("직전 거절 사유 미언급")
            feedback.append(
                f"직전 거절 사유('{rejection.get('reason', '')}')를 설명에서 직접 언급하고 어떻게 보완했는지 적으세요."
            )
        if not element:
            issues = ", ".join(ISSUE_LABELS.get(i, i) for i in rejection.get("issues") or []) or "문제 요소"
            feedback.append(f"거절에서 지목된 {issues}를 무엇으로 바꿨는지 적으세요.")
    else:
        answered = REVIEW_ITEM_MAX if responds else 0
        if not responds:
            blocking.append("변경 이벤트 미대응")
            feedback.append(f"변경 이벤트('{state['event'].get('detail', '')}')에 어떻게 대응하는지 적으세요.")

    # 엔진이 비용과 거리를 이미 점수에 넣었으므로 여기서는 늘어난 비용의 이유를 적었는지만 본다.
    optimization = REVIEW_ITEM_MAX
    if candidate["extraCost"] > 0 and not quoted(checks.cost_reason, text, COST_WORDS, COST_CAUSE):
        optimization = 10
        feedback.append(f"추가 비용 {candidate['extraCost']:,}원이 왜 드는지 적으세요.")

    items = [u for u in plan["unresolved"] if not any(mark in u for mark in SYSTEM_UNRESOLVED)]
    filled = sum(0.5 * bool(OWNER.search(u)) + 0.5 * bool(DEADLINE.search(u)) for u in items)
    vague = [u for u in items if not (OWNER.search(u) and DEADLINE.search(u))]
    risk = round(REVIEW_ITEM_MAX * filled / len(items)) if items else REVIEW_ITEM_MAX
    if vague:
        feedback.append(f"미확정 항목에 담당과 기한을 적으세요: {', '.join(vague[:3])}")

    breakdown = {
        "evidence": evidence,
        "rejection": answered,
        "optimization": optimization,
        "explanation": explanation,
        "risk": risk,
    }
    uncited = set(empty) - set(citable)
    no_more_evidence = state.get("info_retries", 0) >= MAX_INFO_RETRIES or bool(state.get("evidence_stalled"))
    action = "MORE_EVIDENCE" if uncited and not no_more_evidence else "REWRITE"
    # 남은 사유가 더 찾을 수도, 이미 찾은 것에서 인용할 수도 없는 근거뿐이면 고쳐도 같은 사유로 회차만 쓴다.
    stuck = blocking == ["근거 0건 범주"] and not citable and no_more_evidence
    return {"breakdown": breakdown, "blocking": blocking, "feedback": feedback, "action": action, "stuck": stuck}


def _rejection_line(rejection: dict[str, Any] | None) -> str:
    if not rejection:
        return "없음"
    issues = ", ".join(ISSUE_LABELS.get(i, i) for i in rejection.get("issues") or []) or "지정 없음"
    return f"거절 사유: {rejection.get('reason', '')} / 문제 요소: {issues}"


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
    """승인 요청 전에 안을 점검합니다. 통과 점수 미만이거나 통과를 막는 사유가 있으면 고쳐서 다시 검토하고,
    상한 회차에 닿으면 그때까지 가장 나았던 안으로 승인을 요청합니다."""
    limits = ctx.settings.limits
    plan = state["selected_plan"]
    candidate = plan["candidate"]
    round_no = state.get("review_round", 0) + 1
    # 앞 회차 점수는 넣지 않는다. 낮은 점수를 보면 고친 안도 낮게 매기는 경향이 평가에서 확인됐다.
    body = fit_sections(
        [
            Section("업무 규칙 엔진이 확인한 사실", review_facts(candidate), 0),
            Section("변경안", describe(candidate), 0),
            Section("변경 이벤트", state["event"].get("detail") or _json(state["event"]), 0),
            Section("직전 거절", _json(state.get("last_rejection")) if state.get("last_rejection") else "없음", 0),
            Section("설명", plan["explanation"], 0),
        ],
        ctx.settings.context_token_budget,
    )
    checks = await ctx.model.structured(
        ctx,
        [SystemMessage(_system()), HumanMessage(render("self_review", questions=review_questions(plan, state), context=body))],
        ReviewChecks,
    )
    scored = score_review(checks, plan, state)
    breakdown, blocking = scored["breakdown"], scored["blocking"]
    score = sum(breakdown.values())
    passed = score >= limits.review_pass_score and not blocking
    # 근거 말고는 통과 점수를 넘었고 그 근거를 더 구할 방법이 없으면, 남은 회차를 쓰지 않고 지금까지 가장 나은 안으로 넘긴다.
    # 빈 범주는 미확정 항목에 '근거 조항 확인 필요'로 남아 승인자가 본다.
    stuck = not passed and scored["stuck"] and score >= limits.review_pass_score
    history = [
        *(state.get("review_history") or []),
        {
            "round": round_no,
            "score": score,
            "passed": passed,
            "hash": plan["hash"],
            "action": scored["action"],
            "breakdown": breakdown,
            "blocking": blocking,
            "feedback": scored["feedback"],
        },
    ]
    # 상한 회차에서 올릴 안은 통과를 막는 사유가 없는 안을 먼저, 그다음 점수가 높은 안을 고른다.
    best = state.get("best_review")
    if best is None or (not blocking, score) > (not best.get("blocking"), best["score"]):
        best = {"score": score, "round": round_no, "plan": plan, "blocking": blocking}

    update: dict[str, Any] = {"review_round": round_no, "review_history": history, "best_review": best}
    # 점수는 코드가 계산하므로 생각 기록도 코드가 쓴다. 수정 요청 대상은 아니다(판단 근거가 규칙이라 고칠 곳이 설명 단계다).
    update["_thought"] = {
        "observation": f"{round_no}회차 {score}점 (근거 {breakdown['evidence']}, 거절과 사건 대응 {breakdown['rejection']}, "
        f"비용 이유 {breakdown['optimization']}, 설명 {breakdown['explanation']}, 미확정 관리 {breakdown['risk']})",
        "decision": "승인 요청"
        if passed
        else ("가장 나은 안으로 승인 요청" if round_no >= limits.max_review_rounds or stuck else "다시 고치기"),
        "reason": "; ".join(blocking + scored["feedback"][:2]) or "통과 기준을 모두 넘었습니다",
    }
    if passed or stuck or round_no >= limits.max_review_rounds:
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
                    else (
                        f"더 찾을 근거가 없어 가장 나은 {best['round']}회차 {best['score']}점 안으로 승인 요청"
                        if stuck and round_no < limits.max_review_rounds
                        else f"{limits.max_review_rounds}회 도달, 가장 나은 {best['round']}회차 {best['score']}점 안으로 승인 요청"
                    )
                ),
            }
        )
        return update

    action = scored["action"]
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
    if action == "MORE_EVIDENCE" and (state.get("info_retries", 0) >= MAX_INFO_RETRIES or state.get("evidence_stalled")):
        action = "REWRITE"
    # 이력에는 실제로 실행한 행동을 남겨야 다음 회차의 정체 판단과 화면 표시가 맞는다.
    history[-1]["action"] = action
    update["review_feedback"] = scored["feedback"]
    if action == "NEXT_CANDIDATE":
        update.update({"review_skipped": skipped, "review_next": "compose_plan"})
    elif action == "MORE_EVIDENCE":
        weak = [c["constraint"] for c in plan["checklist"] if c["status"] == "WARN" or not c["evidenceIds"]]
        update.update({"missing_info": weak or list(HARD_CONSTRAINTS), "review_next": "collect_constraints"})
    else:
        update["review_next"] = "compose_plan"
    labels = {"REWRITE": "설명과 근거 보완", "NEXT_CANDIDATE": "다른 조합으로 교체", "MORE_EVIDENCE": "규정 근거 추가 검색"}
    reason = f"통과를 막는 사유({', '.join(blocking)})가 있어" if blocking else f"{limits.review_pass_score}점 미만이라"
    update["_detail"] = f"{round_no}회차 {score}점, {reason} {labels[action]}: {'; '.join(scored['feedback'][:2])}"
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
        if hit["doc_type"] == "DATA":
            # 조회 결과는 rag 문서가 아니라 대조할 원문이 없다.
            cited.append(
                {
                    "id": cid,
                    "doc_id": hit["doc_id"],
                    "title": f"{hit['title']} / {hit['heading']}",
                    "text": hit["text"],
                    "doc_type": "DATA",
                }
            )
            continue
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
        # 계획 Agent 카드를 승인 대기로 바꾼다. APPROVAL_REQUIRED보다 먼저 나가야 backend 상태가 승인 대기로 남는다.
        "_agent_status": "waiting",
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
                "_thought": thought_of(
                    rejection,
                    {
                        "observation": f"{decision.get('role')} 거절: {decision.get('reason', '')}",
                        "decision": rejection.summary,
                        "reason": "거절 사유를 다음 루프의 추가 제약으로 바꿉니다",
                    },
                ),
                "_revisable": False,
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


_EXEC_GRAPH: list[Any] = []


def _exec_graph():
    """실행팀 subgraph를 한 번만 컴파일합니다. checkpointer 없이 컴파일하면 부모 그래프의 체크포인터를 이어 씁니다."""
    if not _EXEC_GRAPH:
        _EXEC_GRAPH.append(build_execution_graph().compile())
    return _EXEC_GRAPH[0]


@harnessed("execute", "실행팀", agent=None)
async def execute(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """확정된 안을 실행팀 subgraph에 넘깁니다. 실행 수정 요청이면 이전 보고와 함께 넘겨 지목한 Agent만 다시 돌게 합니다."""
    order = state.get("revise_order")
    prior = state.get("exec_reports") or []
    # 실행팀은 도구 한도와 시간을 계획 단계와 따로 센다. 계획 단계에서 이미 쓴 호출 수 때문에 실행이 중간에 멈추지 않게 한다.
    sub_ctx = dataclasses.replace(ctx, counter=new_counter())
    exec_graph = ctx.exec_graph or _exec_graph()
    result = await exec_graph.ainvoke(
        {
            "facts": execution_facts(state),
            "prior_reports": prior if order else [],
            "revise_order": order,
            "step_seq": int(state.get("step_seq") or 0) + 1,
            "loop_counter": new_counter(),
            "rounds": 0,
            "stage": 0,
            "retries": {},
            "skipped": [],
        },
        {"recursion_limit": 40},
        context=sub_ctx,
    )
    add_usage_to(ctx.counter, result.get("loop_counter") or {})
    new_reports = result.get("exec_reports") or []
    latest = latest_reports({"prior_reports": prior if order else [], "exec_reports": new_reports})
    reports = [{k: latest[a][k] for k in ("agent", "status", "summary", "artifacts")} for a in AGENTS if a in latest]
    budget = (latest.get("ledger") or {}).get("artifacts", {}).get("budget")
    outcome = result.get("outcome") or DONE
    execution = {
        "status": outcome,
        "reason": result.get("reason", ""),
        "reports": reports,
        "skipped": [a for a in result.get("skipped") or [] if a not in latest],
        "budget": budget,
    }
    done = [AGENT_LABELS[r["agent"]] for r in reports if r["status"] == DONE]
    return {
        "exec_reports": [*prior, *new_reports],
        "execution": execution,
        "revise_order": None,
        "stop_condition": None if outcome == DONE else EXEC_NEEDS_HUMAN,
        "step_seq": int(result.get("step_seq") or 0),
        "_detail": f"실행 {outcome}: {', '.join(done) or '완료한 Agent 없음'}",
    }


@harnessed("publish", "공지와 알림")
async def publish(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """확정과 실행 결과를 완료 이벤트로 알립니다. 콜시트 배포와 알림 발송은 backend Outbox와 Worker가 맡습니다."""
    plan = state["selected_plan"]
    evidence = state.get("evidence") or {}
    cited = sorted({cid for item in plan["checklist"] for cid in item["evidenceIds"]})
    execution = state.get("execution") or {}
    answer = (
        f"변경안 {state['approvals']['version_no']}이 전원 승인되어 확정되었습니다. "
        f"{describe(plan['candidate'])}. 콜시트 v{state['callsheet_version_no']} 배포를 요청했습니다."
    )
    if execution:
        done = [AGENT_LABELS[r["agent"]] for r in execution.get("reports") or [] if r["status"] == DONE]
        answer += f" 실행팀 처리: {', '.join(done) or '없음'}."
        if execution.get("status") != DONE:
            answer += f" {execution.get('reason', '')}"
    result = {
        "answer": answer,
        "sources": [
            {"docId": evidence[c]["doc_id"], "title": evidence[c]["title"], "snippet": evidence[c]["text"][:160]} for c in cited
        ],
        "proposalId": state["approvals"]["proposal_id"],
        "callsheetVersionNo": state["callsheet_version_no"],
        "execution": execution or None,
    }
    if state.get("stop_condition") == EXEC_NEEDS_HUMAN:
        # 확정은 되돌리지 않는다. 남은 일을 사람에게 넘기는 결과로 끝낸다.
        result.update({"reason": STOP_MESSAGES[EXEC_NEEDS_HUMAN], "stopCondition": EXEC_NEEDS_HUMAN})
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
                + feedback_block(state)
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
        # 대체 장소가 들어오면 그 장소의 허가 조항을 새로 찾아야 한다.
        "evidence_stalled": False,
        "alternatives": registered,
        "suggestions": suggestions,
        "stop_condition": None if registered or early else NO_FEASIBLE_PLAN,
        "_thought": thought_of(
            keywords,
            {
                "observation": situation,
                "decision": f"검색 키워드 {', '.join(keywords.keywords)}",
                "reason": "세 안의 장소 특징과 씬 의도에서 뽑았습니다",
            },
        ),
        "_revisable": True,
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
