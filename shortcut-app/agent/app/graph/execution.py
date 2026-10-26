"""확정 뒤 실행팀 subgraph입니다. supervisor가 실행 Agent 6개를 의존 순서대로 3단계로 보냅니다.

1단계 장소 예약, 장비 렌탈(서로 독립)
2단계 촬영 허가, 이동 수단(장소가 확정돼야 함)
3단계 출연진/스태프 연락, 제작비 장부(앞 단계 결과가 모두 있어야 함)

단계 순서는 업무 규칙이라 코드 표(STAGES)로 고정하고, 각 단계에서 누구를 보낼지만 supervisor LLM이 고릅니다.
같은 단계의 Agent는 Send로 동시에 실행하고, 보고는 exec_reports(add 리듀서)로 모읍니다.
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import Limits
from app.graph.common import add_usage_to, harnessed, run_tool_loop, thought_of
from app.graph.schemas import ExecutionNote, SupervisorDecision
from app.harness.instructions import render
from app.harness.tools import ToolOutcome
from app.runtime import RunContext

STAGES: dict[int, tuple[str, ...]] = {1: ("venue", "rental"), 2: ("permit", "transport"), 3: ("contact", "ledger")}
STAGE_OF = {agent: stage for stage, agents in STAGES.items() for agent in agents}
AGENTS = tuple(agent for agents in STAGES.values() for agent in agents)
# 이 Agent의 결과가 바뀌면 다시 돌려야 하는 뒤 단계 Agent다. 차량 대수는 장비 부피에 따라 바뀌므로 렌탈 뒤에 이동이 온다.
DEPENDENTS: dict[str, tuple[str, ...]] = {
    "venue": ("permit", "transport", "contact", "ledger"),
    "rental": ("transport", "contact", "ledger"),
    "permit": ("contact", "ledger"),
    "transport": ("contact", "ledger"),
    "contact": (),
    "ledger": (),
}
AGENT_LABELS = {
    "venue": "장소 예약",
    "rental": "장비 렌탈",
    "permit": "촬영 허가",
    "transport": "이동 수단",
    "contact": "출연진/스태프 연락",
    "ledger": "제작비 장부",
}
TOOLS: dict[str, list[str]] = {
    "venue": ["ops_venue_check", "ops_venue_hold", "ops_venue_confirm", "ops_venue_cancel"],
    "rental": ["ops_rental_quote", "ops_rental_book", "ops_rental_cancel"],
    "permit": ["ops_permit_check_requirement", "ops_permit_apply", "ops_permit_status"],
    "transport": ["ops_transport_quote", "ops_transport_book", "ops_transport_cancel"],
    "contact": ["ops_contacts_for_change", "ops_send_message", "ops_get_replies"],
    "ledger": ["ops_ledger_record", "ops_ledger_budget_status"],
}
# 실행 Agent 모두에게 붙이는 기본 조건이다. 승인된 확정안 범위 밖으로 바꾸는 것은 사람의 승인 없이 할 수 없다.
BASE_CONSTRAINTS = [
    "승인된 확정안의 장소, 시간대, 장비 밖으로 바꾸지 않습니다",
    "실패하면 억지로 다른 방법을 쓰지 말고 이유를 남깁니다",
]
# 오후 블록 배우 외에 이동하는 스태프 수다. 시드 콜시트의 팀 다섯 곳(연출, 촬영, 조명, 동시녹음, 미술)을 두 명씩 잡았다.
CREW_HEADCOUNT = 10
DONE, FAILED, NEEDS_HUMAN = "DONE", "FAILED", "NEEDS_HUMAN"
CARD_STATUS = {DONE: "done", FAILED: "failed", NEEDS_HUMAN: "needs_human"}


class ExecState(TypedDict, total=False):
    """실행팀 subgraph의 상태입니다. 부모 그래프와 분리해 실행팀만 따로 테스트할 수 있습니다."""

    facts: dict[str, Any]
    # 수정 요청 재실행 때 이전 실행의 보고. 다시 돌리지 않는 Agent의 결과(예약 번호 등)를 뒤 단계에 넘기는 데 쓴다
    prior_reports: list[dict[str, Any]]
    revise_order: dict[str, Any] | None
    step_seq: int
    loop_counter: dict[str, Any]
    exec_reports: Annotated[list[dict[str, Any]], operator.add]
    exec_usage: Annotated[list[dict[str, Any]], operator.add]
    usage_merged: int
    stage: int
    rounds: int
    retries: dict[str, int]
    # 수정 요청 재실행에서 다시 돌릴 Agent. None이면 모두 대상이다
    redo: list[str] | None
    # 직전 라운드에 보낸 Agent와 이번 라운드에 보낼 지시서
    last_sent: list[str]
    sends: list[dict[str, Any]]
    skipped: list[str]
    outcome: str | None
    reason: str


def execution_facts(state: dict[str, Any]) -> dict[str, Any]:
    """확정안과 원래 안의 차이를 실행 Agent가 쓸 사실로 정리합니다. 바뀐 요소는 코드가 계산합니다."""
    plan = state["selected_plan"]["candidate"]
    plan_set = state.get("plan_set") or {}
    current = plan_set.get("current") or {}
    original_location = current.get("location") or {}
    original_equipment = sorted(item.get("id") for item in current.get("equipment") or [])
    items = plan["equipment"]["items"]
    changed = []
    if plan["location"]["id"] != original_location.get("id"):
        changed.append("LOCATION")
    if (plan["time"]["start"], plan["time"]["end"]) != (current.get("start"), current.get("end")):
        changed.append("TIME")
    if sorted(item["id"] for item in items) != original_equipment:
        changed.append("EQUIPMENT")
    if plan.get("extraCost", 0) > 0:
        changed.append("COST")
    actors = (plan_set.get("block") or {}).get("actorIds") or []
    return {
        "taskId": int(state["task_id"]),
        "shootDayId": state["shoot_day_id"],
        "location": {"id": plan["location"]["id"], "name": plan["location"]["name"], "indoor": plan["location"]["indoor"]},
        "originalLocation": {"id": original_location.get("id"), "name": original_location.get("name")},
        "start": plan["time"]["start"],
        "end": plan["time"]["end"],
        "originalStart": current.get("start"),
        "originalEnd": current.get("end"),
        "equipment": [{"id": item["id"], "name": item["name"]} for item in items],
        "originalEquipmentIds": original_equipment,
        "drone": any("드론" in item["name"] for item in items),
        "headcount": len(actors) + CREW_HEADCOUNT,
        "changed": changed,
        "costKrw": plan.get("cost", 0),
        "extraCostKrw": plan.get("extraCost", 0),
        "event": (state.get("event") or {}).get("detail", ""),
        "unresolved": state["selected_plan"].get("unresolved") or [],
    }


def latest_reports(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Agent마다 가장 최근 보고입니다. 수정 요청으로 다시 돌린 Agent는 새 보고가 이전 보고를 덮습니다."""
    latest: dict[str, dict[str, Any]] = {}
    for report in [*(state.get("prior_reports") or []), *(state.get("exec_reports") or [])]:
        latest[report["agent"]] = report
    return latest


def needed(agent: str, facts: dict[str, Any]) -> bool | None:
    """코드가 판단할 수 있는 필요 여부입니다. True면 반드시 보내고, False면 보내지 않으며, None이면 supervisor가 정합니다."""
    changed = set(facts["changed"])
    if agent == "venue":
        return True if changed & {"LOCATION", "TIME"} else None
    if agent == "rental":
        return True if "EQUIPMENT" in changed else None
    if agent == "permit":
        # 실내 스튜디오는 장소 예약이 곧 사용 허락이고, 드론이 없으면 비행 승인도 필요 없다.
        if facts["location"]["indoor"] and not facts["drone"]:
            return False
        return True if changed & {"LOCATION", "TIME", "EQUIPMENT"} else None
    if agent == "transport":
        return True if "LOCATION" in changed else None
    # 연락과 장부는 바뀐 것이 있으면 항상 3단계에서 한다.
    return True


def _order(agent: str, goal: str, constraints: list[str] | None = None) -> dict[str, Any]:
    return {"agent": agent, "goal": goal, "constraints": [*BASE_CONSTRAINTS, *(constraints or [])]}


def _prior_for(state: dict[str, Any]) -> dict[str, Any]:
    """뒤 단계 Agent에게 넘길 앞 단계 결과입니다. 성공한 보고의 결과물만 넘깁니다."""
    return {
        agent: {"summary": report["summary"], "artifacts": report["artifacts"]}
        for agent, report in latest_reports(state).items()
        if report["status"] == DONE
    }


def _payload(state: dict[str, Any], order: dict[str, Any], stage: int, round_no: int, comment: str | None) -> dict[str, Any]:
    return {
        "agent": order["agent"],
        "order": order,
        "facts": state["facts"],
        "prior": _prior_for(state),
        "stage": stage,
        "round": round_no,
        "comment": comment,
        # 같은 단계에서 동시에 도는 Agent는 supervisor 다음 순번을 함께 쓴다.
        "step_seq": int(state.get("step_seq") or 0) + 1,
        "loop": (state.get("loop_counter") or {}).get("loops", 1),
    }


def _skip_events(agents: list[str], reason: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("AGENT", {"agent": a, "node": f"{a}_agent", "stage": STAGE_OF[a], "status": "skipped", "action": reason}) for a in agents
    ]


async def _decide(
    ctx: RunContext, state: dict[str, Any], stage: int, candidates: list[str], comment: str | None
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    """이번 단계에 보낼 Agent와 지시서를 정합니다. 3단계와 꼭 필요한 Agent는 코드가 정하고 나머지는 LLM이 고릅니다."""
    facts = state["facts"]
    forced = [a for a in candidates if needed(a, facts) is True]
    optional = [a for a in candidates if needed(a, facts) is None]
    orders: dict[str, dict[str, Any]] = {}
    thought = None
    if optional or (forced and stage < 3):
        decision = await ctx.model.structured(
            ctx,
            [
                SystemMessage(render("exec_system")),
                HumanMessage(
                    render(
                        "exec_supervisor",
                        stage=stage,
                        candidates="\n".join(f"- {a}: {AGENT_LABELS[a]}" for a in candidates),
                        forced=", ".join(forced) or "없음",
                        facts=_json(facts),
                        reports=_json(_prior_for(state)),
                        comment=comment or "없음",
                    )
                ),
            ],
            SupervisorDecision,
        )
        thought = thought_of(
            decision,
            {
                "observation": f"{stage}단계 후보 {', '.join(candidates)}, 바뀐 요소 {', '.join(facts['changed']) or '없음'}",
                "decision": ", ".join(o.agent for o in decision.orders) or "보낼 Agent 없음",
                "reason": "바뀐 요소에 필요한 Agent만 보냅니다",
            },
        )
        for order in decision.orders:
            # 이번 단계 후보가 아닌 Agent(예: 1단계에 연락)는 보내지 않는다. 의존 순서는 코드가 지킨다.
            if order.agent in candidates and needed(order.agent, facts) is not False:
                orders[order.agent] = _order(order.agent, order.goal, order.constraints)
    for agent in forced:
        orders.setdefault(agent, _order(agent, DEFAULT_GOALS[agent]))
    return [orders[a] for a in candidates if a in orders], thought


DEFAULT_GOALS = {
    "venue": "확정 장소를 확정 시간대로 예약 확정하고, 더는 쓰지 않는 이전 장소 예약은 취소합니다",
    "rental": "확정안의 장비 묶음을 확보하고, 더는 쓰지 않는 이전 렌탈은 취소합니다",
    "permit": "확정 장소와 시간대에 필요한 촬영 허가(드론 포함)를 받습니다",
    "transport": "오전 촬영지에서 확정 장소까지 인원과 장비를 옮길 차량을 예약합니다",
    "contact": "영향받는 배우, 스태프, 업체에게 바뀐 내용과 확정된 예약 정보를 사람마다 맞춰 알립니다",
    "ledger": "이번 변경으로 생긴 비용과 취소 수수료를 장부에 기록하고 예산 대비 집행을 확인합니다",
}


@harnessed("supervisor", "실행팀 지휘", agent="supervisor", phase="exec", revisable=True)
async def supervisor(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """앞 단계 보고를 확인하고 다음 단계에 보낼 Agent를 정합니다. 실패하면 뒤 단계로 넘어가지 않습니다."""
    limits = ctx.settings.limits
    usage = state.get("exec_usage") or []
    for item in usage[state.get("usage_merged", 0) :]:
        add_usage_to(ctx.counter, item)
    rounds = state.get("rounds", 0)
    stage = state.get("stage", 0)
    retries = dict(state.get("retries") or {})
    redo = state.get("redo")
    revise = state.get("revise_order") or {}
    comment = revise.get("comment") if revise else None
    update: dict[str, Any] = {"usage_merged": len(usage)}

    if rounds == 0 and revise:
        target = revise.get("agent")
        # 실행 Agent를 지목했으면 그 Agent와 그 결과에 기대는 뒤 단계 Agent만 다시 보낸다.
        # supervisor 판단을 지목했으면 모든 단계를 다시 보되, 요청을 반영해 누구를 보낼지 다시 고른다.
        redo = [target, *DEPENDENTS[target]] if target in DEPENDENTS else None
        update["redo"] = redo

    last_sent = state.get("last_sent") or []
    finished = [r for r in state.get("exec_reports") or [] if r.get("round") == rounds and r["agent"] in last_sent]
    bad = [r for r in finished if r["status"] != DONE]

    def stop(outcome: str, reason: str, thought: dict[str, str]) -> dict[str, Any]:
        return {**update, "outcome": outcome, "reason": reason, "sends": [], "_thought": thought, "_detail": reason}

    if rounds >= limits.max_exec_rounds:
        reason = f"실행팀 판단 횟수 상한({limits.max_exec_rounds}회)에 도달했습니다"
        return stop(
            NEEDS_HUMAN, reason, {"observation": reason, "decision": "사람에게 넘김", "reason": "끝나지 않는 반복을 막습니다"}
        )

    if bad:
        names = ", ".join(AGENT_LABELS[r["agent"]] for r in bad)
        summaries = " / ".join(f"{AGENT_LABELS[r['agent']]}: {r['summary']}" for r in bad)
        retry = [r for r in bad if r["status"] == FAILED and retries.get(r["agent"], 0) < 1]
        if len(retry) == len(bad):
            sends = []
            for report in retry:
                retries[report["agent"]] = retries.get(report["agent"], 0) + 1
                order = _order(
                    report["agent"],
                    DEFAULT_GOALS[report["agent"]],
                    [f"이전 시도가 실패했습니다: {report['summary']}. 같은 실패를 반복하지 않도록 도구 결과를 먼저 확인합니다"],
                )
                sends.append(
                    _payload(state, order, stage, rounds + 1, comment if report["agent"] == revise.get("agent") else None)
                )
            return {
                **update,
                "retries": retries,
                "rounds": rounds + 1,
                "sends": sends,
                "last_sent": [s["agent"] for s in sends],
                "_thought": {
                    "observation": f"{names} 실패: {summaries}",
                    "decision": f"{names}에게 한 번 더 지시합니다",
                    "reason": "앞 단계가 끝나지 않으면 뒤 단계 Agent를 보내지 않습니다. 일시적인 실패일 수 있어 한 번은 다시 시킵니다",
                },
                "_detail": f"{names} 재지시",
            }
        reason = f"{names} 처리가 끝나지 않아 뒤 단계를 멈추고 사람에게 넘깁니다"
        return stop(
            NEEDS_HUMAN,
            reason,
            {
                "observation": summaries,
                "decision": "뒤 단계를 보내지 않고 사람에게 넘김",
                "reason": "다시 시켜도 해결되지 않는 실패이거나 이미 한 번 다시 시켰습니다. 확정 장소가 없는데 연락이 나가면 사고입니다",
            },
        )

    skipped = list(state.get("skipped") or [])
    events: list[tuple[str, dict[str, Any]]] = []
    thoughts: list[dict[str, str]] = []
    while True:
        stage += 1
        if stage > 3:
            latest = latest_reports(state)
            done = [AGENT_LABELS[a] for a in AGENTS if a in latest and latest[a]["status"] == DONE]
            reason = f"실행 완료: {', '.join(done) or '실행할 일이 없었습니다'}"
            thought = (
                thoughts[-1]
                if thoughts
                else {
                    "observation": f"완료한 Agent: {', '.join(done) or '없음'}",
                    "decision": "실행을 마칩니다",
                    "reason": "세 단계를 모두 확인했고 실패한 Agent가 없습니다",
                }
            )
            return {**stop(DONE, reason, thought), "stage": stage, "skipped": skipped, "_events": events}
        candidates = [a for a in STAGES[stage] if redo is None or a in redo]
        if redo is not None and revise.get("agent") in DEPENDENTS:
            # 수정 요청 재실행에서는 지목한 Agent와, 이전에 실제로 돌았던 뒤 단계 Agent만 다시 보낸다.
            ran_before = set(latest_reports({"prior_reports": state.get("prior_reports")}))
            candidates = [a for a in candidates if a == revise["agent"] or a in ran_before]
            orders = [
                _order(
                    a,
                    DEFAULT_GOALS[a],
                    [f"사용자 수정 요청: {comment}"]
                    if a == revise["agent"]
                    else ["앞 단계 결과가 바뀌어 다시 처리합니다. 바뀐 결과에 맞춰 정정합니다"],
                )
                for a in candidates
                if needed(a, state["facts"]) is not False
            ]
            thought = {
                "observation": f"사용자가 {AGENT_LABELS[revise['agent']]} 결과 수정을 요청했습니다: {comment}",
                "decision": f"{stage}단계에서 {', '.join(AGENT_LABELS[o['agent']] for o in orders) or '보낼 Agent 없음'}",
                "reason": "지목한 Agent와 그 결과에 기대는 뒤 단계 Agent만 다시 실행하고, 나머지 결과는 그대로 씁니다",
            }
        else:
            orders, thought = await _decide(ctx, state, stage, candidates, comment)
        chosen = [o["agent"] for o in orders]
        not_chosen = [a for a in STAGES[stage] if a not in chosen and (redo is None or a in redo)]
        skipped += [a for a in not_chosen if a not in skipped]
        events += _skip_events(not_chosen, "이번 변경에는 필요 없어 보내지 않음")
        if thought:
            thoughts.append(thought)
        if orders:
            break

    sends = [_payload(state, order, stage, rounds + 1, comment) for order in orders]
    labels = ", ".join(AGENT_LABELS[o["agent"]] for o in orders)
    return {
        **update,
        "stage": stage,
        "rounds": rounds + 1,
        "sends": sends,
        "last_sent": [s["agent"] for s in sends],
        "skipped": skipped,
        "outcome": None,
        "_events": events,
        "_thought": thoughts[-1] if thoughts else None,
        "_detail": f"{stage}단계: {labels}",
    }


def route(state: dict[str, Any]) -> list[Send] | str:
    """supervisor가 정한 지시서를 Send로 바꿉니다. 같은 단계의 Agent는 동시에 실행됩니다."""
    if state.get("outcome") or not state.get("sends"):
        return END
    return [Send(f"{s['agent']}_agent", s) for s in state["sends"]]


# ---------------------------------------------------------------- 실행 Agent의 결과 판정 (코드)


def _ok(outcomes: list[ToolOutcome], tool: str) -> list[dict[str, Any]]:
    return [o.data for o in outcomes if o.ok and o.name == tool and isinstance(o.data, dict)]


def ledger_refs(prior: dict[str, Any]) -> list[dict[str, str]]:
    """앞 단계 결과에서 장부에 기록할 수 있는 예약 번호를 모읍니다.

    렌탈처럼 건너뛴 Agent는 결과가 없으므로 그 계정의 번호도 없습니다. 이 목록을 장부 Agent에 주지 않으면
    모델이 장부 양식의 렌탈 항목을 채우려고 번호를 지어내고, 없는 번호 하나 때문에 기록 전체가 거절됐습니다.
    """
    refs: list[dict[str, str]] = []

    def add(account, ref_type, ref_id):
        if ref_id:
            refs.append({"account": account, "ref_type": ref_type, "ref_id": str(ref_id)})

    for agent, account, ref_type, key in (
        ("venue", "VENUE", "RESERVATION", "reservationId"),
        ("rental", "EQUIPMENT_RENTAL", "RENTAL", "bookingId"),
        ("transport", "TRANSPORT", "TRANSPORT", "bookingId"),
    ):
        artifacts = (prior.get(agent) or {}).get("artifacts") or {}
        add(account, ref_type, artifacts.get(key))
        for cancelled in artifacts.get("cancelled") or []:
            add("CANCEL_FEE", ref_type, cancelled.get(key))
    for permit in ((prior.get("permit") or {}).get("artifacts") or {}).get("permits") or []:
        if permit.get("status") == "APPROVED":
            add("PERMIT_FEE", "PERMIT", permit.get("permitId"))
    return refs


def _cancelled(outcomes: list[ToolOutcome], tool: str, key: str) -> list[dict[str, Any]]:
    return [{key: d.get(key), "cancelFeeKrw": d.get("cancelFeeKrw", 0)} for d in _ok(outcomes, tool)]


def judge_venue(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    target, start, end = facts["location"]["id"], facts["start"], facts["end"]
    confirmed = [d for d in _ok(outcomes, "ops_venue_confirm") if d.get("status") == "CONFIRMED"]
    # 같은 장소와 시간대에 이미 확정된 예약이 있으면 확인만으로 끝난 것으로 본다.
    existing = [
        r
        for d in _ok(outcomes, "ops_venue_check")
        for r in d.get("reservations") or []
        if r.get("locationId") == target and r.get("status") == "CONFIRMED" and (r.get("start"), r.get("end")) == (start, end)
    ]
    holds = _ok(outcomes, "ops_venue_hold")
    artifacts: dict[str, Any] = {"location": facts["location"]["name"], "time": f"{start}~{end}"}
    final = confirmed[-1] if confirmed else (existing[-1] if existing else None)
    if final:
        artifacts.update(reservationId=final["reservationId"], status="CONFIRMED", priceKrw=final.get("priceKrw"))
    elif holds:
        artifacts.update(reservationId=holds[-1]["reservationId"], status=holds[-1].get("status", "HELD"))
    cancelled = _cancelled(outcomes, "ops_venue_cancel", "reservationId")
    if cancelled:
        artifacts["cancelled"] = cancelled
    return (DONE if final else FAILED), artifacts


def judge_rental(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    booked = _ok(outcomes, "ops_rental_book")
    quotes = _ok(outcomes, "ops_rental_quote")
    artifacts: dict[str, Any] = {"equipment": ", ".join(item["name"] for item in facts["equipment"])}
    status = FAILED
    if booked:
        last = booked[-1]
        artifacts.update(bookingId=last["bookingId"], totalKrw=last.get("totalKrw"), deliveryAt=last.get("deliveryAt"))
        status = DONE
    elif quotes and all(item.get("owned") for item in quotes[-1].get("items") or []):
        artifacts.update(note="보유 장비만 써서 새로 빌릴 장비가 없습니다", totalKrw=0)
        status = DONE
    cancelled = _cancelled(outcomes, "ops_rental_cancel", "bookingId")
    if cancelled:
        artifacts["cancelled"] = cancelled
    return status, artifacts


def judge_permit(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requirements = _ok(outcomes, "ops_permit_check_requirement")
    applied = _ok(outcomes, "ops_permit_apply")
    if requirements and not requirements[-1].get("required"):
        return DONE, {"note": "이 장소와 장비에는 촬영 허가가 필요 없습니다"}
    kinds = list(requirements[-1].get("kinds") or []) if requirements else sorted({d.get("kind") for d in applied})
    approved = {d["kind"]: d for d in applied if d.get("status") == "APPROVED"}
    denied = [d for d in applied if d.get("status") == "DENIED"]
    artifacts: dict[str, Any] = {
        "permits": [
            {k: d.get(k) for k in ("permitId", "kind", "status", "feeKrw", "conditions", "denialReason")} for d in applied
        ]
    }
    if denied:
        # 가상 허가 기관의 반려는 같은 신청을 다시 해도 바뀌지 않으므로 다시 시키지 않고 사람에게 넘긴다.
        artifacts["denied"] = [d.get("denialReason") for d in denied]
        return NEEDS_HUMAN, artifacts
    return (DONE if kinds and all(k in approved for k in kinds) else FAILED), artifacts


def judge_transport(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    booked = _ok(outcomes, "ops_transport_book")
    artifacts: dict[str, Any] = {}
    if booked:
        last = booked[-1]
        artifacts.update(
            {k: last.get(k) for k in ("bookingId", "costKrw", "departAt", "pickup")},
            vehicle=last.get("vehicle"),
            count=last.get("count"),
        )
    cancelled = _cancelled(outcomes, "ops_transport_cancel", "bookingId")
    if cancelled:
        artifacts["cancelled"] = cancelled
    return (DONE if booked else FAILED), artifacts


def judge_contact(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    sent = sum(len(d.get("sent") or []) for d in _ok(outcomes, "ops_send_message"))
    replies = _ok(outcomes, "ops_get_replies")
    artifacts: dict[str, Any] = {"sent": sent}
    if replies:
        last = replies[-1]
        artifacts.update(acked=last.get("acked"), pending=last.get("pending"), questions=last.get("questions") or [])
    return (DONE if sent else FAILED), artifacts


def judge_ledger(outcomes: list[ToolOutcome], facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    records = _ok(outcomes, "ops_ledger_record")
    statuses = _ok(outcomes, "ops_ledger_budget_status")
    artifacts: dict[str, Any] = {}
    if records:
        artifacts["entries"] = sum(len(d.get("entries") or []) for d in records)
        artifacts["recordedKrw"] = sum(d.get("totalKrw", 0) for d in records)
    budget = (statuses[-1] if statuses else (records[-1].get("budget") if records else None)) or {}
    if budget:
        artifacts["budget"] = {k: budget.get(k) for k in ("capKrw", "spentKrw", "remainingKrw", "over")}
    return (DONE if records else FAILED), artifacts


JUDGES = {
    "venue": judge_venue,
    "rental": judge_rental,
    "permit": judge_permit,
    "transport": judge_transport,
    "contact": judge_contact,
    "ledger": judge_ledger,
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _tool_log(outcomes: list[ToolOutcome]) -> str:
    lines = [f"- {o.name} {'성공' if o.ok else '실패'}: {o.content[:300]}" for o in outcomes]
    return "\n".join(lines) or "도구를 부르지 않았습니다"


def _fixed_args(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """안내문 발송에 작업 번호와 실행 라운드를 코드가 넣습니다. 백엔드가 이 둘과 받는 사람으로 중복을 가려,
    재시도로 노드가 다시 돌며 모델이 문장을 새로 써도 같은 라운드에는 한 번만 보냅니다."""
    return {"ops_send_message": {"task_id": state["facts"]["taskId"], "round": state["round"]}}


def make_agent(name: str):
    """실행 Agent 노드를 만듭니다. 도구는 LLM이 고르고, 성공 여부와 결과물은 코드가 도구 결과로 판정합니다."""

    @harnessed(f"{name}_agent", AGENT_LABELS[name], agent=name, phase="exec", parallel=True, revisable=True, stage=STAGE_OF[name])
    async def node(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
        facts = state["facts"]
        system = render("exec_system")
        user = render(
            f"exec_{name}",
            order=_json(state["order"]),
            facts=_json(facts),
            prior=_json(state.get("prior") or {}),
            comment=state.get("comment") or "없음",
            refs=_json(ledger_refs(state.get("prior") or {})),
        )
        outcomes, last = await run_tool_loop(
            ctx, system, user, TOOLS[name], ctx.settings.limits.max_exec_tool_rounds, fixed_args=_fixed_args(state)
        )
        status, artifacts = JUDGES[name](outcomes, facts)
        note = await ctx.model.structured(
            ctx,
            [
                SystemMessage(system),
                HumanMessage(
                    render(
                        "exec_report",
                        agent=AGENT_LABELS[name],
                        order=_json(state["order"]),
                        status=status,
                        artifacts=_json(artifacts),
                        log=_tool_log(outcomes),
                        reply=str(last.content or "")[:500],
                    )
                ),
            ],
            ExecutionNote,
        )
        if status == FAILED and note.needs_human:
            status = NEEDS_HUMAN
        report = {
            "agent": name,
            "stage": STAGE_OF[name],
            "round": state["round"],
            "status": status,
            "summary": note.summary,
            "artifacts": artifacts,
        }
        return {
            "exec_reports": [report],
            "_thought": thought_of(
                note,
                {"observation": _json(artifacts)[:200], "decision": note.summary, "reason": f"도구 결과로 판정한 상태 {status}"},
            ),
            "_agent_status": CARD_STATUS[status],
            "_detail": f"{AGENT_LABELS[name]} {status}: {note.summary}",
        }

    node.__name__ = f"{name}_agent"
    return node


def build_execution_graph(limits: Limits | None = None) -> StateGraph:
    """실행팀 StateGraph를 만듭니다. 부모 그래프의 체크포인터를 그대로 쓰므로 checkpointer 없이 compile합니다."""
    graph = StateGraph(ExecState, context_schema=RunContext)
    graph.add_node("supervisor", supervisor)
    for agent in AGENTS:
        graph.add_node(f"{agent}_agent", make_agent(agent))
        graph.add_edge(f"{agent}_agent", "supervisor")
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route, [f"{a}_agent" for a in AGENTS] + [END])
    return graph
