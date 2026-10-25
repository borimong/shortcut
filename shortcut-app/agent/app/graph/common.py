"""노드 공통 실행 규칙(진행 이벤트, 시간 측정)과 LLM 도구 선택 반복을 담습니다."""

from __future__ import annotations

import copy
import dataclasses
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime

from app.harness.context import trim_messages
from app.harness.limits import new_counter, stop_condition
from app.harness.tools import ToolOutcome
from app.runtime import RunContext

NodeFn = Callable[[dict[str, Any], RunContext], Awaitable[dict[str, Any]]]


def harnessed(
    node: str,
    label: str,
    *,
    event_node: str | None = None,
    announce_start: bool = True,
    agent: str | None = "planner",
    phase: str = "plan",
    parallel: bool = False,
    revisable: bool = False,
    stage: int | None = None,
):
    """노드 시작과 끝을 NODE, AGENT 이벤트로 알리고, 노드가 남긴 생각(_thought)을 THOUGHT 이벤트로 보냅니다.

    step은 State의 step_seq이고 노드 하나가 끝날 때마다 1씩 오릅니다. 계획 단계 수정 요청은 이 값으로
    그 노드 직전 체크포인트를 찾습니다. agent가 None이면 Agent 카드를 움직이지 않습니다(실행팀을 부르는 껍데기 노드).
    parallel은 Send로 동시에 도는 실행 Agent용입니다. 병렬 노드가 같은 키(loop_counter, step_seq)를 함께 쓰면
    LangGraph가 충돌 오류를 내므로, 노드마다 컨텍스트 사본과 새 카운터를 쓰고 사용량은 exec_usage에만 남깁니다.
    """

    def decorator(fn: NodeFn):
        # functools.wraps를 쓰면 LangGraph가 원래 함수의 (state, ctx) 시그니처를 보고 runtime을 넘기지 않으므로 이름과 설명만 옮긴다.
        async def wrapper(state: dict[str, Any], runtime: Runtime[RunContext]) -> dict[str, Any]:
            base = runtime.context
            if parallel:
                ctx = dataclasses.replace(base, counter=new_counter(), agent=agent or base.agent)
            else:
                ctx = base
                ctx.counter = copy.deepcopy(state.get("loop_counter") or new_counter())
                if agent:
                    ctx.agent = agent
            ctx.store = runtime.store
            shown = event_node or node
            step = int(state.get("step_seq") or 0)
            loop = ctx.counter["loops"] if not parallel else int(state.get("loop") or 1)
            card = {"agent": agent, "node": shown, **({"stage": stage} if stage else {})}
            if announce_start:
                await ctx.events.publish("NODE", {"node": shown, "label": label, "phase": "start", "loop": loop})
                if agent:
                    await ctx.events.publish("AGENT", {**card, "status": "running", "action": label})
            started = time.monotonic()
            try:
                update = dict(await fn(state, ctx) or {})
            except GraphBubbleUp:
                # 승인 대기(interrupt)는 실패가 아니라 멈춤이다. 대기 표시는 request_approval이 승인 요청 이벤트보다 먼저 보냈다.
                # backend는 멈추기 직전 마지막 이벤트(APPROVAL_REQUIRED)로 작업 상태를 정하므로 여기서는 아무것도 보내지 않는다.
                raise
            except Exception:
                if agent:
                    await ctx.events.publish("AGENT", {**card, "status": "failed", "action": label})
                raise
            finally:
                # interrupt로 멈추는 경우에도 그때까지 쓴 시간은 남겨야 하므로 finally에서 더한다.
                spent = int((time.monotonic() - started) * 1000)
                ctx.counter["elapsed_ms"] += spent
                ctx.counter["loop_elapsed_ms"] = ctx.counter.get("loop_elapsed_ms", 0) + spent
            detail = update.pop("_detail", None)
            thought = update.pop("_thought", None)
            can_revise = update.pop("_revisable", revisable)
            agent_status = update.pop("_agent_status", "done")
            # 노드가 남긴 상태 이벤트(APPROVAL_REQUIRED)는 NODE 끝 이벤트 뒤에 보내야 backend가 마지막 상태를 승인 대기로 기록한다.
            follow_ups = update.pop("_events", [])
            await ctx.events.publish("NODE", {"node": shown, "label": label, "phase": "end", "loop": loop, "detail": detail})
            if thought:
                await ctx.events.publish(
                    "THOUGHT",
                    {
                        "step": step,
                        "node": shown,
                        "agent": agent or ctx.agent,
                        "phase": phase,
                        "loop": loop,
                        "observation": thought.get("observation", ""),
                        "decision": thought.get("decision", ""),
                        "reason": thought.get("reason", ""),
                        "revisable": bool(can_revise),
                    },
                )
            if agent:
                action = detail if isinstance(detail, str) and detail else label
                await ctx.events.publish("AGENT", {**card, "status": agent_status, "action": action[:120]})
            for event_type, payload in follow_ups:
                await ctx.events.publish(event_type, payload)
            if parallel:
                update["exec_usage"] = [usage_of(ctx.counter)]
            else:
                update["loop_counter"] = ctx.counter
                # 실행팀을 부르는 노드는 subgraph가 쓴 순번을 그대로 이어 받는다.
                update.setdefault("step_seq", step + 1)
            return update

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


USAGE_KEYS = ("tool_calls", "llm_calls", "tokens", "cost_usd", "retries", "fallbacks")


def usage_of(counter: dict[str, Any]) -> dict[str, Any]:
    """카운터에서 합산할 사용량만 뽑습니다. 시간은 병렬로 겹치므로 넣지 않고 부모 노드의 경과 시간으로 잽니다."""
    return {key: counter.get(key, 0) for key in USAGE_KEYS}


def add_usage_to(counter: dict[str, Any], usage: dict[str, Any]) -> None:
    for key in USAGE_KEYS:
        counter[key] = (
            round(counter.get(key, 0) + usage.get(key, 0), 6) if key == "cost_usd" else counter.get(key, 0) + usage.get(key, 0)
        )


def thought_of(model: Any, fallback: dict[str, str] | None = None) -> dict[str, str] | None:
    """구조화 출력의 thought 필드를 이벤트에 실을 dict로 바꿉니다.
    모델이 thought를 빼먹어도 작업은 이어 가야 하므로, 그때는 노드가 코드로 만든 기본 생각(fallback)을 씁니다."""
    thought = getattr(model, "thought", None)
    if thought is None:
        return fallback
    dumped = thought.model_dump()
    if fallback:
        dumped = {k: v or fallback.get(k, "") for k, v in dumped.items()}
    return dumped


def feedback_block(state: dict[str, Any]) -> str:
    """사용자가 생각 기록에서 고른 수정 요청입니다. 판단 노드 프롬프트 끝에 붙여 반드시 반영하게 합니다."""
    items = state.get("user_feedback") or []
    if not items:
        return ""
    return "\n\n## 사용자 수정 요청 (반드시 반영)\n" + "\n".join(f"- {item}" for item in items)


async def run_tool_loop(
    ctx: RunContext, system: str, user: str, allowed: list[str], max_rounds: int
) -> tuple[list[ToolOutcome], AIMessage]:
    """모델이 허용된 도구 가운데 필요한 것을 고르고, Harness가 실행해 결과를 돌려주는 반복입니다."""
    specs = await ctx.tools.specs(allowed)
    messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
    outcomes: list[ToolOutcome] = []
    last = AIMessage(content="")
    for _ in range(max_rounds):
        messages = trim_messages(messages, ctx.settings.context_token_budget)
        last = await ctx.model.chat(ctx, messages, specs)
        messages.append(last)
        if not last.tool_calls:
            break
        for call in last.tool_calls:
            outcome = await ctx.tools.call(ctx, call["name"], call["args"], allowed=allowed)
            outcomes.append(outcome)
            messages.append(
                ToolMessage(
                    content=outcome.content,
                    tool_call_id=call["id"],
                    name=call["name"],
                    status="success" if outcome.ok else "error",
                )
            )
        if stop_condition(ctx.counter, ctx.settings.limits):
            break
    return outcomes, last


async def call_tool_or_raise(ctx: RunContext, name: str, args: dict[str, Any], *, approved: bool = False) -> Any:
    """코드가 순서를 정한 도구 호출입니다. 실패하면 작업 재시도로 넘기려고 예외를 냅니다."""
    outcome = await ctx.tools.call(ctx, name, args, allowed=[name], approved=approved)
    if not outcome.ok:
        raise ToolCallError(outcome)
    return outcome.data


class ToolCallError(RuntimeError):
    """코드가 직접 부른 도구가 실패했을 때 냅니다."""

    def __init__(self, outcome: ToolOutcome):
        super().__init__(outcome.content)
        self.outcome = outcome
