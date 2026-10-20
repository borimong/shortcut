"""Agent Loop의 실행량을 세고 멈춤 조건을 판정합니다."""

from __future__ import annotations

from typing import Any

from app.config import Limits

# 멈춤 조건 코드다. 화면과 평가 결과표가 같은 코드를 쓴다.
LOOP_LIMIT = "LOOP_LIMIT"
TOOL_LIMIT = "TOOL_LIMIT"
TIME_LIMIT = "TIME_LIMIT"
NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"

STOP_MESSAGES = {
    LOOP_LIMIT: "재계획 루프 한도에 도달했습니다",
    TOOL_LIMIT: "도구 호출 한도에 도달했습니다",
    TIME_LIMIT: "자동 탐색 시간 한도에 도달했습니다",
    NO_FEASIBLE_PLAN: "하드 제약을 모두 지키는 후보가 없습니다",
    MODEL_UNAVAILABLE: "모델 호출이 재시도와 대체 모델까지 실패했습니다",
}


def new_counter() -> dict[str, Any]:
    """State에 저장하는 실행량 카운터를 만듭니다. 체크포인트와 함께 저장되어 재개 후에도 이어진다."""
    return {
        "loops": 1,
        "tool_calls": 0,
        "llm_calls": 0,
        "elapsed_ms": 0,
        "loop_elapsed_ms": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "retries": 0,
        "fallbacks": 0,
        "signatures": {},
    }


def stop_condition(counter: dict[str, Any], limits: Limits) -> str | None:
    """한도를 넘었으면 멈춤 조건 코드를, 아니면 None을 돌려줍니다."""
    if counter["loops"] > limits.max_loops:
        return LOOP_LIMIT
    if counter["tool_calls"] > limits.max_tool_calls:
        return TOOL_LIMIT
    # 승인 대기 시간은 노드 밖에서 흐르므로 들어가지 않고, 거절로 새 루프가 시작되면 0부터 다시 센다.
    if counter.get("loop_elapsed_ms", counter["elapsed_ms"]) > limits.max_seconds * 1000:
        return TIME_LIMIT
    return None
