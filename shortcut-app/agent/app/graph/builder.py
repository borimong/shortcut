"""노드를 Edge로 연결해 재계획 그래프를 만듭니다. 분기마다 멈춤 조건을 먼저 확인합니다."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import Limits
from app.graph import nodes
from app.graph.state import ReplanState
from app.harness.limits import new_counter, stop_condition
from app.runtime import RunContext


def guarded(limits: Limits, route: Callable[[dict[str, Any]], str]) -> Callable[[dict[str, Any]], str]:
    """한도를 넘었으면 원래 분기 대신 사람에게 보고하는 노드로 보냅니다."""

    def wrapper(state: dict[str, Any]) -> str:
        if stop_condition(state.get("loop_counter") or new_counter(), limits):
            return "report_human"
        return route(state)

    wrapper.__name__ = f"guarded_{route.__name__}"
    return wrapper


def after_collect(state: dict[str, Any]) -> str:
    # 첫 검색에서 빠진 범주가 있으면 그 범주만 한 번 더 찾게 한다.
    if state.get("missing_info") and state.get("info_retries", 0) < 2:
        return "collect_constraints"
    return "reevaluate_plans"


def when_exhausted(state: dict[str, Any]) -> str:
    # 1/2/3안이 바닥나면 한 번은 4안을 구성해 보고, 4안까지 막히면 사람에게 넘긴다.
    return "report_human" if state.get("alternatives_tried") else "suggest_alternatives"


def after_reevaluate(state: dict[str, Any]) -> str:
    return "compose_plan" if state.get("feasible_count", 0) > 0 else when_exhausted(state)


def after_compose(state: dict[str, Any]) -> str:
    if state.get("selected_plan") is None:
        return when_exhausted(state)
    if state.get("missing_info") and state.get("info_retries", 0) < nodes.MAX_INFO_RETRIES:
        return "collect_constraints"
    # 자체 검토에서 설명만 고친 경우에는 같은 후보라 검증 게이트를 다시 거치지 않는다.
    if state["selected_plan"]["hash"] == state.get("validated_hash"):
        return "self_review"
    return "validation_gate"


def after_gate(state: dict[str, Any]) -> str:
    return {"PASS": "self_review", "VIOLATION": "compose_plan", "STALE": "reevaluate_plans"}[state["gate_result"]]


def after_review(state: dict[str, Any]) -> str:
    return state["review_next"]


def after_request(state: dict[str, Any]) -> str:
    return "await_approval" if (state.get("approvals") or {}).get("proposal_id") else "reevaluate_plans"


def after_approval(state: dict[str, Any]) -> str:
    return "commit_plan" if state["approvals"]["decision"] == "APPROVED" else "reevaluate_plans"


def after_alternatives(state: dict[str, Any]) -> str:
    return "reevaluate_plans" if state.get("alternatives") else "report_human"


def after_commit(state: dict[str, Any]) -> str:
    return "publish" if state.get("callsheet_version_no") else "reevaluate_plans"


def build_replan_graph(limits: Limits) -> StateGraph:
    """재계획 StateGraph를 만듭니다. compile은 checkpointer와 store를 가진 쪽에서 합니다."""
    graph = StateGraph(ReplanState, context_schema=RunContext)
    for name in (
        "detect_change",
        "analyze_impact",
        "collect_constraints",
        "reevaluate_plans",
        "compose_plan",
        "validation_gate",
        "self_review",
        "request_approval",
        "await_approval",
        "commit_plan",
        "publish",
        "suggest_alternatives",
        "report_human",
    ):
        graph.add_node(name, getattr(nodes, name))

    graph.add_edge(START, "detect_change")
    graph.add_conditional_edges("detect_change", guarded(limits, lambda s: "analyze_impact"), ["analyze_impact", "report_human"])
    graph.add_conditional_edges(
        "analyze_impact", guarded(limits, lambda s: "collect_constraints"), ["collect_constraints", "report_human"]
    )
    graph.add_conditional_edges(
        "collect_constraints", guarded(limits, after_collect), ["collect_constraints", "reevaluate_plans", "report_human"]
    )
    graph.add_conditional_edges(
        "reevaluate_plans", guarded(limits, after_reevaluate), ["compose_plan", "suggest_alternatives", "report_human"]
    )
    graph.add_conditional_edges(
        "compose_plan",
        guarded(limits, after_compose),
        ["validation_gate", "self_review", "collect_constraints", "suggest_alternatives", "report_human"],
    )
    graph.add_conditional_edges(
        "validation_gate",
        guarded(limits, after_gate),
        ["self_review", "compose_plan", "reevaluate_plans", "report_human"],
    )
    graph.add_conditional_edges(
        "self_review",
        guarded(limits, after_review),
        ["request_approval", "compose_plan", "collect_constraints", "report_human"],
    )
    graph.add_conditional_edges(
        "request_approval", guarded(limits, after_request), ["await_approval", "reevaluate_plans", "report_human"]
    )
    graph.add_conditional_edges(
        "await_approval", guarded(limits, after_approval), ["commit_plan", "reevaluate_plans", "report_human"]
    )
    # 확정은 이미 사람이 승인한 결과라 한도를 넘었다는 이유로 멈추지 않는다.
    graph.add_conditional_edges("commit_plan", after_commit, ["publish", "reevaluate_plans"])
    graph.add_edge("publish", END)
    graph.add_conditional_edges("suggest_alternatives", guarded(limits, after_alternatives), ["reevaluate_plans", "report_human"])
    graph.add_edge("report_human", END)
    return graph
