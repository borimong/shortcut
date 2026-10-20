"""노드 공통 실행 규칙(진행 이벤트, 시간 측정)과 LLM 도구 선택 반복을 담습니다."""

from __future__ import annotations

import copy
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from app.harness.context import trim_messages
from app.harness.limits import new_counter, stop_condition
from app.harness.tools import ToolOutcome
from app.runtime import RunContext

NodeFn = Callable[[dict[str, Any], RunContext], Awaitable[dict[str, Any]]]


def harnessed(node: str, label: str, *, event_node: str | None = None, announce_start: bool = True):
    """노드 시작과 끝을 NODE 이벤트로 알리고 실행 시간을 카운터에 더합니다."""

    def decorator(fn: NodeFn):
        # functools.wraps를 쓰면 LangGraph가 원래 함수의 (state, ctx) 시그니처를 보고 runtime을 넘기지 않으므로 이름과 설명만 옮긴다.
        async def wrapper(state: dict[str, Any], runtime: Runtime[RunContext]) -> dict[str, Any]:
            ctx = runtime.context
            ctx.store = runtime.store
            ctx.counter = copy.deepcopy(state.get("loop_counter") or new_counter())
            shown = event_node or node
            if announce_start:
                await ctx.events.publish("NODE", {"node": shown, "label": label, "phase": "start", "loop": ctx.counter["loops"]})
            started = time.monotonic()
            try:
                update = dict(await fn(state, ctx) or {})
            finally:
                # interrupt로 멈추는 경우에도 그때까지 쓴 시간은 남겨야 하므로 finally에서 더한다.
                spent = int((time.monotonic() - started) * 1000)
                ctx.counter["elapsed_ms"] += spent
                ctx.counter["loop_elapsed_ms"] = ctx.counter.get("loop_elapsed_ms", 0) + spent
            detail = update.pop("_detail", None)
            # 노드가 남긴 상태 이벤트(APPROVAL_REQUIRED)는 NODE 끝 이벤트 뒤에 보내야 backend가 마지막 상태를 승인 대기로 기록한다.
            follow_ups = update.pop("_events", [])
            update["loop_counter"] = ctx.counter
            await ctx.events.publish(
                "NODE", {"node": shown, "label": label, "phase": "end", "loop": ctx.counter["loops"], "detail": detail}
            )
            for event_type, payload in follow_ups:
                await ctx.events.publish(event_type, payload)
            return update

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


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
