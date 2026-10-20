"""모델 호출 실패를 재시도와 대체 모델로 복구합니다."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import openai

T = TypeVar("T")

# 429(요청 한도)와 503(일시 과부하)은 잠시 뒤 같은 요청이 성공하는 경우가 많아 재시도 대상으로 둔다.
RETRYABLE_STATUS = {429, 503}
# 재시도는 2회까지만 한다. 그 이상 기다리면 120초 작업 한도를 대기만으로 소진한다.
MAX_RETRIES = 2
BASE_DELAY_SECONDS = 1.0


class ModelUnavailableError(RuntimeError):
    """재시도와 대체 모델까지 모두 실패했을 때 냅니다."""


def is_retryable(error: Exception) -> bool:
    """같은 요청을 다시 보내면 성공할 수 있는 오류인지 판정합니다."""
    if isinstance(error, openai.APIStatusError):
        return error.status_code in RETRYABLE_STATUS
    return isinstance(error, (openai.APITimeoutError, openai.APIConnectionError))


async def call_with_recovery(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]] | None,
    *,
    on_retry: Callable[[], None] = lambda: None,
    on_fallback: Callable[[], None] = lambda: None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """기본 모델을 지수 백오프로 재시도하고, 계속 실패하면 대체 모델을 한 번 부릅니다."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await primary()
        except Exception as error:
            if not is_retryable(error):
                raise
            last_error = error
            if attempt < MAX_RETRIES:
                on_retry()
                await sleep(BASE_DELAY_SECONDS * (2**attempt))
    if fallback is not None:
        on_fallback()
        try:
            return await fallback()
        except Exception as error:
            if not is_retryable(error):
                raise
            last_error = error
    raise ModelUnavailableError(str(last_error)) from last_error
