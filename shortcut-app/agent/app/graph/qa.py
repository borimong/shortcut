"""변경안에 대한 근거 질문에 모델이 도구를 골라 답하는 그래프입니다."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graph.common import harnessed, run_tool_loop
from app.graph.state import QaState
from app.harness.context import Section, fit_sections
from app.harness.instructions import render
from app.runtime import RunContext

QA_TOOLS = [
    "business_get_proposal",
    "business_get_plan_set",
    "business_get_entity_context",
    "business_get_weather",
    "business_get_disaster_alerts",
    "business_get_actor_schedule",
    "business_find_unplaceable_scenes",
    "rag_search_regulation",
    "rag_search_contract_clause",
    "rag_search_script",
]


@harnessed("analyze_impact", "근거 조회")
async def gather(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """질문에 필요한 업무 데이터와 규정 근거를 모델이 고른 도구로 모읍니다."""
    proposal = f"변경안 ID {state['proposal_id']}" if state.get("proposal_id") else "지정한 변경안 없음"
    user = render("qa_gather", question=state["question"], proposal=proposal)
    outcomes, _ = await run_tool_loop(ctx, render("qa_system"), user, QA_TOOLS, ctx.settings.limits.max_node_tool_rounds)
    evidence: dict[str, dict[str, Any]] = {}
    results = []
    for outcome in outcomes:
        if not outcome.ok:
            continue
        if outcome.name.startswith("rag_"):
            for hit in outcome.data:
                evidence[hit["chunk_id"]] = hit
        else:
            # 변경안에는 승인 단계에서 원문 대조를 마친 근거 조항이 이미 들어 있어 그대로 인용 후보로 쓴다.
            if outcome.name == "business_get_proposal":
                for item in outcome.data.get("evidence") or []:
                    evidence[item["id"]] = {
                        "doc_id": item["docId"],
                        "title": item["title"],
                        "heading": "",
                        "text": item["text"],
                        "doc_type": item.get("docType", ""),
                    }
            results.append({"tool": outcome.name, "data": outcome.content})
    return {"tool_results": results, "evidence": evidence, "_detail": f"도구 {len(outcomes)}회, 근거 {len(evidence)}건"}


@harnessed("publish", "답변 생성")
async def answer(state: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """모은 근거만으로 답하고 인용한 chunk_id를 출처로 남깁니다. 답변은 TOKEN 이벤트로 흘려보낸다."""
    evidence = state.get("evidence") or {}
    body = fit_sections(
        [
            Section("질문", state["question"], 0),
            Section(
                "규정 근거",
                "\n".join(f"[{cid}] {h['title']} / {h['heading']}: {h['text']}" for cid, h in evidence.items()) or "없음",
                1,
            ),
            Section("업무 데이터", "\n".join(r["data"] for r in state.get("tool_results") or []) or "없음", 2),
        ],
        ctx.settings.context_token_budget,
    )
    text = await ctx.model.stream_text(ctx, [SystemMessage(render("qa_system")), HumanMessage(render("qa_answer", context=body))])
    return {"answer": text, "_detail": f"답변 {len(text)}자"}


def build_qa_graph() -> StateGraph:
    graph = StateGraph(QaState, context_schema=RunContext)
    graph.add_node("gather", gather)
    graph.add_node("answer", answer)
    graph.add_edge(START, "gather")
    graph.add_edge("gather", "answer")
    graph.add_edge("answer", END)
    return graph
