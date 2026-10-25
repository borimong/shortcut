"""RabbitMQ agent.tasks 큐의 작업을 받아 그래프를 시작하거나 승인 결과로 재개합니다."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

import aio_pika
import httpx
from langchain_core.tracers.context import collect_runs
from langgraph.types import Command

from app.config import Settings
from app.harness.instructions import prompt_versions
from app.harness.limits import new_counter
from app.harness.model import ModelGateway
from app.harness.observability import BackendEventPublisher, TaskCancelled, log_event, run_config, trace_url_for
from app.harness.recovery import PermanentError
from app.harness.tools import McpConnections, ToolGateway
from app.runtime import RunContext

EXCHANGE = "shortcut"
TASK_QUEUE = "agent.tasks"
RETRY_QUEUE = "agent.tasks.retry"
DEAD_LETTER_QUEUE = "agent.tasks.dlq"
# 일시 장애(LLM 과부하, MCP 재시작)는 몇 초 뒤 회복되는 경우가 많아 세 번까지 다시 넣는다.
MAX_ATTEMPTS = 3

_CITATION = re.compile(r"\[([a-z0-9\-]+#\d+)\]")


async def check_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractExchange:
    """backend가 선언한 exchange와 큐가 있는지 확인만 합니다.

    RabbitMQ는 큐 인자의 정수 타입까지 비교해서 Java Integer와 Python int로 같은 TTL을 선언해도 거부하므로,
    토폴로지는 backend 한 곳이 소유하고 Agent는 passive로 존재만 확인한다. 없으면 예외가 나고 소비자가 재연결을 반복한다.
    """
    exchange = await channel.get_exchange(EXCHANGE, ensure=True)
    for name in (TASK_QUEUE, RETRY_QUEUE, DEAD_LETTER_QUEUE):
        await channel.get_queue(name, ensure=True)
    return exchange


class TaskRunner:
    """작업 메시지 하나를 그래프 실행 한 번으로 바꿉니다."""

    def __init__(self, settings: Settings, replan_graph, qa_graph, model: ModelGateway, http: httpx.AsyncClient):
        self.settings = settings
        self.replan_graph = replan_graph
        self.qa_graph = qa_graph
        self.model = model
        self.http = http

    async def run(self, message: dict[str, Any]) -> None:
        task_id = message["taskId"]
        trace_id = message.get("traceId") or uuid.uuid4().hex
        events = BackendEventPublisher(self.http, task_id, trace_id)
        settings = self.settings
        urls = {"business": settings.business_mcp_url, "rag": settings.rag_mcp_url, "ops": settings.ops_mcp_url}
        async with McpConnections(urls, message.get("requestedBy")) as clients:
            tools = ToolGateway(
                clients,
                timeout_seconds=settings.tool_timeout_seconds,
                max_chars=settings.tool_result_max_chars,
                max_same_calls=settings.limits.max_same_tool_calls,
            )
            ctx = RunContext(task_id, trace_id, settings, self.model, tools, events)
            config = {
                "configurable": {"thread_id": message["threadId"]},
                "recursion_limit": 60,
                **run_config(task_id, trace_id, message["kind"], prompt_versions(), message["threadId"]),
            }
            started = time.monotonic()
            with collect_runs() as runs:
                if message["kind"] == "ASK":
                    final = await self._ask(message, config, ctx)
                else:
                    final = await self._replan(message, config, ctx)
            if final is None:
                return
            run_id = str(runs.traced_runs[0].id) if runs.traced_runs else None
            # 링크 조회는 trace 전송을 기다리느라 몇 초 걸릴 수 있어 이벤트 루프를 막지 않게 스레드에서 돌린다.
            trace_url = await asyncio.to_thread(trace_url_for, run_id)
            await self._finish(events, final, trace_url, int((time.monotonic() - started) * 1000))

    async def _replan(self, message: dict[str, Any], config: dict, ctx: RunContext) -> dict[str, Any] | None:
        graph = self.replan_graph
        snapshot = await graph.aget_state(config)
        if message["action"] == "REVISE":
            if not await self._revise(message["revise"], config, ctx):
                return None
        elif message["action"] == "RESUME":
            if not snapshot.next:
                log_event("resume_after_finish_ignored", trace_id=ctx.trace_id, task_id=ctx.task_id)
                return None
            # 큐는 같은 메시지를 두 번 보낼 수 있으므로, 이전 변경안의 결정이 늦게 와서 새 변경안에 반영되지 않게 막는다.
            waiting_for = (snapshot.values.get("approvals") or {}).get("proposal_id")
            if message.get("proposalId") is not None and message["proposalId"] != waiting_for:
                log_event(
                    "stale_resume_ignored", trace_id=ctx.trace_id, proposal_id=message["proposalId"], waiting_for=waiting_for
                )
                return None
            # 승인 결과를 이미 반영한 뒤 다음 노드에서 실패해 재시도된 경우에는 결과를 다시 넣지 않고 이어 간다.
            payload = Command(resume=message["resume"]) if "await_approval" in snapshot.next else None
            await graph.ainvoke(payload, config, context=ctx)
        elif snapshot.next:
            # 재시도로 같은 START가 다시 오면 처음부터 하지 않고 마지막 체크포인트에서 이어 간다.
            if "await_approval" in snapshot.next:
                log_event("duplicate_start_ignored", trace_id=ctx.trace_id, task_id=ctx.task_id)
                return None
            await graph.ainvoke(None, config, context=ctx)
        else:
            task = await self._task(ctx.task_id)
            initial = {
                "task_id": ctx.task_id,
                "thread_id": message["threadId"],
                "shoot_day_id": task["shootDayId"],
                "event": {
                    "id": task["eventId"],
                    "type": task["eventType"],
                    "detail": task["eventDetail"],
                    "instruction": task.get("instruction") or "",
                    "requested_by": task.get("requestedBy"),
                    "changes": task.get("eventChanges") or [],
                },
                "max_loops": task.get("maxLoops") or self.settings.limits.max_loops,
                "extra_constraints": [],
                "failed_hashes": [],
                "violations": [],
                "loop_summaries": [],
                "info_retries": 0,
                "loop_counter": new_counter(),
            }
            await graph.ainvoke(initial, config, context=ctx)

        state = await graph.aget_state(config)
        if state.next:
            # 승인 대기로 멈춘 상태다. APPROVAL_REQUIRED는 request_approval 노드가 이미 보냈다.
            return None
        return {"values": state.values, "kind": "REPLAN"}

    async def _revise(self, revise: dict[str, Any], config: dict, ctx: RunContext) -> bool:
        """사용자가 생각 기록에서 고른 판단 하나를 고쳐 다시 실행합니다. 처리했으면 True를 돌려줍니다."""
        graph = self.replan_graph
        comment = f"{revise.get('node', '')} 판단에 대해: {revise['comment']}"
        event_id = revise.get("eventId")
        latest = await graph.aget_state(config)
        if event_id is not None and event_id in (latest.values.get("revisions_done") or []):
            # 이미 반영한 요청이다. 반영 뒤 다음 노드에서 실패해 재시도된 경우에만 마지막 체크포인트에서 이어 간다.
            if latest.next and "await_approval" not in latest.next:
                await graph.ainvoke(None, config, context=ctx)
                return True
            log_event("duplicate_revise_ignored", trace_id=ctx.trace_id, task_id=ctx.task_id, event_id=event_id)
            return False
        done = [*(latest.values.get("revisions_done") or []), event_id]
        if revise.get("phase") == "exec":
            # 실행 단계는 외부에 예약과 발송이 이미 남았으므로 되감지 않는다. 확정 직후 지점부터 실행팀을 다시 시작하고,
            # supervisor가 지목한 Agent와 그 결과에 기대는 뒤 단계 Agent만 다시 보낸다(취소 후 재예약, 정정 안내).
            await graph.aupdate_state(
                config,
                {"revise_order": {"agent": revise["agent"], "comment": revise["comment"]}, "revisions_done": done},
                as_node="commit_plan",
            )
            await graph.ainvoke(None, config, context=ctx)
            return True
        # 계획 단계는 타임 트래블이다. 그 노드가 실행되기 직전(같은 step_seq, 다음 노드가 그 노드)의 체크포인트를 찾아
        # 사용자 요청을 넣은 분기를 만들고 거기서부터 다시 돈다. 앞 단계 결과는 그대로 재사용된다.
        target = None
        async for past in graph.aget_state_history(config):
            if revise["node"] in (past.next or ()) and int(past.values.get("step_seq") or 0) == int(revise["step"]):
                target = past
                break
        if target is None:
            log_event("revise_target_not_found", trace_id=ctx.trace_id, task_id=ctx.task_id, step=revise.get("step"))
            await ctx.events.publish(
                "FAILED", {"error": "수정 요청한 판단의 체크포인트를 찾지 못했습니다. 변경을 다시 입력해 주세요."}
            )
            return False
        feedback = [*(target.values.get("user_feedback") or []), comment]
        forked = await graph.aupdate_state(target.config, {"user_feedback": feedback, "revisions_done": done})
        await graph.ainvoke(None, forked, context=ctx)
        return True

    async def _ask(self, message: dict[str, Any], config: dict, ctx: RunContext) -> dict[str, Any]:
        task = await self._task(ctx.task_id)
        initial = {
            "task_id": ctx.task_id,
            "question": task["question"],
            "proposal_id": task.get("proposalId"),
            "loop_counter": new_counter(),
        }
        values = await self.qa_graph.ainvoke(initial, config, context=ctx)
        return {"values": values, "kind": "ASK"}

    async def _finish(self, events: BackendEventPublisher, final: dict[str, Any], trace_url: str | None, wall_ms: int) -> None:
        values = final["values"]
        counter = values.get("loop_counter") or new_counter()
        metrics = {
            "loops": counter["loops"],
            "toolCalls": counter["tool_calls"],
            "llmCalls": counter["llm_calls"],
            "tokens": counter["tokens"],
            "costUsd": counter["cost_usd"],
            "latencyMs": counter["elapsed_ms"],
            "wallMs": wall_ms,
            "retries": counter["retries"],
            "fallbacks": counter["fallbacks"],
            "reviewRounds": (values.get("review_result") or {}).get("rounds"),
            "reviewScore": (values.get("review_result") or {}).get("score"),
        }
        if final["kind"] == "ASK":
            evidence = values.get("evidence") or {}
            cited = [cid for cid in _CITATION.findall(values.get("answer", "")) if cid in evidence] or list(evidence)
            sources = [
                {
                    "docId": evidence[c]["doc_id"],
                    "title": f"{evidence[c]['title']} / {evidence[c]['heading']}",
                    "snippet": evidence[c]["text"][:160],
                    "chunkId": c,
                }
                for c in dict.fromkeys(cited)
            ]
            await events.publish(
                "DONE", {"answer": values.get("answer", ""), "sources": sources, "traceUrl": trace_url, "metrics": metrics}
            )
            return
        result = values.get("result") or {}
        if values.get("stop_condition"):
            await events.publish(
                "NEEDS_HUMAN", {**result, "answer": result.get("reason"), "traceUrl": trace_url, "metrics": metrics}
            )
        else:
            await events.publish("DONE", {**result, "traceUrl": trace_url, "metrics": metrics})

    async def _task(self, task_id: str) -> dict[str, Any]:
        response = await self.http.get(f"/internal/ai/tasks/{task_id}")
        response.raise_for_status()
        return response.json()


async def consume(settings: Settings, runner: TaskRunner, http: httpx.AsyncClient, stop: asyncio.Event) -> None:
    """큐를 구독하고, 실패한 작업은 attempt를 올려 retry 큐로, 세 번째 실패는 DLQ로 보냅니다."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        # 작업 하나가 LLM과 도구를 여러 번 부르므로 동시에 너무 많이 받지 않게 4개로 제한한다.
        await channel.set_qos(prefetch_count=4)
        exchange = await check_topology(channel)
        queue = await channel.get_queue(TASK_QUEUE)

        async def handle(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                body = json.loads(message.body)
                attempt = int((message.headers or {}).get("x-attempt", 1))
                try:
                    await runner.run(body)
                except TaskCancelled:
                    # 사람이 중단한 작업이다. 다시 시도하거나 실패로 바꾸지 않고 메시지만 처리한다.
                    log_event("task_cancelled", task_id=body.get("taskId"), trace_id=body.get("traceId"))
                except Exception as error:
                    log_event(
                        "task_failed",
                        task_id=body.get("taskId"),
                        attempt=attempt,
                        error=repr(error),
                        trace_id=body.get("traceId"),
                    )
                    # 다시 해도 같은 오류(설정 누락 등)는 재시도로 토큰과 시간만 쓰므로 바로 DLQ로 보낸다.
                    permanent = isinstance(error, PermanentError)
                    target = RETRY_QUEUE if attempt < MAX_ATTEMPTS and not permanent else DEAD_LETTER_QUEUE
                    await exchange.publish(
                        aio_pika.Message(
                            message.body,
                            headers={"x-attempt": attempt + 1, "x-last-error": repr(error)[:300]},
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            content_type="application/json",
                        ),
                        routing_key=target,
                    )
                    if target == DEAD_LETTER_QUEUE:
                        events = BackendEventPublisher(http, body["taskId"], body.get("traceId") or "")
                        reason = "재시도해도 같은 오류라 바로 실패" if permanent else f"{MAX_ATTEMPTS}회 시도 후 실패"
                        await events.publish("FAILED", {"error": f"{reason}: {error}", "attempts": attempt})

        consumer_tag = await queue.consume(lambda m: asyncio.ensure_future(handle(m)))
        await stop.wait()
        await queue.cancel(consumer_tag)
