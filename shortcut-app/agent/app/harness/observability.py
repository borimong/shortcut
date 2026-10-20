"""진행 이벤트 발행, 구조화 로그, Token 비용 집계, LangSmith trace 연결을 맡습니다."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Protocol

import httpx

logger = logging.getLogger("agent")

# 1M 토큰당 달러 가격(입력, 출력)이다. 실행 결과표의 비용 열을 계산하는 데만 쓴다.
PRICES_PER_MILLION = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}


def log_event(message: str, **fields: Any) -> None:
    """trace_id를 포함한 JSON 한 줄 로그를 남깁니다."""
    logger.info(json.dumps({"msg": message, **fields}, ensure_ascii=False, default=str))


def add_usage(counter: dict[str, Any], model_name: str, usage: dict[str, int] | None) -> None:
    """응답 하나의 토큰 사용량과 비용을 카운터에 더합니다."""
    if not usage:
        return
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    counter["tokens"] += input_tokens + output_tokens
    input_price, output_price = PRICES_PER_MILLION.get(model_name, (0.0, 0.0))
    counter["cost_usd"] = round(counter["cost_usd"] + (input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)


class EventPublisher(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class BackendEventPublisher:
    """backend 내부 API로 진행 이벤트를 보내면 backend가 SSE로 화면에 중계합니다."""

    def __init__(self, client: httpx.AsyncClient, task_id: str, trace_id: str):
        self._client = client
        self._task_id = task_id
        self._trace_id = trace_id

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        # 진행 표시가 늦거나 빠져도 계획 결과는 맞아야 하므로 두 번 시도 후에는 로그만 남기고 그래프를 멈추지 않는다.
        for attempt in range(2):
            try:
                response = await self._client.post(
                    f"/internal/ai/tasks/{self._task_id}/events", json={"type": event_type, "payload": payload}
                )
                response.raise_for_status()
                return
            except httpx.HTTPError as error:
                log_event("event_publish_failed", trace_id=self._trace_id, type=event_type, attempt=attempt, error=str(error))
                await asyncio.sleep(0.5)


def langsmith_enabled() -> bool:
    """LangSmith 키가 있을 때만 trace를 보냅니다."""
    return bool(os.getenv("LANGSMITH_API_KEY")) and os.getenv("LANGSMITH_TRACING", "true").lower() == "true"


def run_config(task_id: str, trace_id: str, kind: str, prompt_versions: dict[str, str]) -> dict[str, Any]:
    """LangSmith에서 작업 하나를 trace_id로 찾을 수 있게 실행 메타데이터를 붙입니다."""
    return {
        "run_name": f"{kind.lower()}-{task_id}",
        "tags": ["shortcut", kind.lower()],
        "metadata": {"task_id": task_id, "trace_id": trace_id, "prompt_versions": prompt_versions},
    }


def trace_url_for(run_id: str | None) -> str | None:
    """LangSmith run 화면 주소를 돌려줍니다. 키가 없거나 조회에 실패하면 None입니다."""
    if not run_id or not langsmith_enabled():
        return None
    try:
        from langsmith import Client

        return Client().read_run(run_id).url
    except Exception as error:
        log_event("trace_url_failed", run_id=run_id, error=str(error))
        return None
