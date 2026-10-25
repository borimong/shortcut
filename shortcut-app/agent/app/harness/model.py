"""모델 호출을 감싸 재시도, 대체 모델, 사용량 집계를 한곳에서 처리합니다."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.harness.observability import add_usage
from app.harness.recovery import call_with_recovery

if TYPE_CHECKING:
    from app.runtime import RunContext

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelGateway:
    """기본 모델과 대체 모델을 갖고 모든 LLM 호출이 이곳을 지나게 합니다."""

    def __init__(self, primary: Any, fallback: Any | None):
        self.primary = primary
        self.fallback = fallback

    @classmethod
    def openai(cls, model: str, fallback_model: str) -> ModelGateway:
        # SDK 자체 재시도를 끄고 recovery 모듈 한 곳에서 재시도 횟수와 대체 모델 전환을 센다.
        def build(name: str) -> ChatOpenAI:
            return ChatOpenAI(model=name, temperature=0, max_retries=0, timeout=30, stream_usage=True)

        return cls(build(model), build(fallback_model))

    async def chat(self, ctx: RunContext, messages: list[BaseMessage], tools: list[dict] | None = None) -> AIMessage:
        """도구 목록을 붙여 다음 행동(답변 또는 도구 호출)을 제안받습니다."""

        def call(model: Any):
            bound = model.bind_tools(tools) if tools else model
            return lambda: bound.ainvoke(messages)

        response = await self._recover(ctx, call)
        add_usage(ctx.counter, _model_name(response), response.usage_metadata)
        return response

    async def structured(self, ctx: RunContext, messages: list[BaseMessage], schema: type[SchemaT]) -> SchemaT:
        """정해진 스키마로 답을 받습니다. 판단 결과를 코드가 검사할 수 있게 하려는 용도다."""

        def call(model: Any):
            # json_schema 엄격 모드는 기본값이 있는 필드를 거부하므로 function_calling 방식으로 받는다.
            bound = model.with_structured_output(schema, method="function_calling", include_raw=True)
            return lambda: bound.ainvoke(messages)

        # 모델이 필수 필드를 빠뜨려 해석에 실패하는 일이 드물게 있어(근거 인용 평가 150개 중 4개), 한 번 다시 묻는다.
        for attempt in range(2):
            result = await self._recover(ctx, call)
            raw = result["raw"]
            add_usage(ctx.counter, _model_name(raw), raw.usage_metadata)
            if not result.get("parsing_error") and result.get("parsed") is not None:
                return result["parsed"]
            if attempt == 0:
                ctx.counter["retries"] = ctx.counter.get("retries", 0) + 1
        raise ValueError(f"구조화 응답 해석 실패: {result.get('parsing_error')}")

    async def stream_text(self, ctx: RunContext, messages: list[BaseMessage]) -> str:
        """답변을 토큰 단위로 TOKEN 이벤트로 내보내면서 전체 문장을 모읍니다."""
        chunks: list[str] = []
        usage = None
        model_name = ""

        async def run(model: Any) -> str:
            nonlocal usage, model_name
            chunks.clear()
            async for chunk in model.astream(messages):
                if chunk.content:
                    chunks.append(chunk.content)
                    await ctx.events.publish("TOKEN", {"text": chunk.content})
                if chunk.usage_metadata:
                    usage = chunk.usage_metadata
                model_name = chunk.response_metadata.get("model_name", model_name)
            return "".join(chunks)

        text = await self._recover(ctx, lambda model: lambda: run(model))
        add_usage(ctx.counter, model_name, usage)
        return text

    async def _recover(self, ctx: RunContext, make_call):
        ctx.counter["llm_calls"] += 1

        def on_retry():
            ctx.counter["retries"] += 1

        def on_fallback():
            ctx.counter["fallbacks"] += 1

        return await call_with_recovery(
            make_call(self.primary),
            make_call(self.fallback) if self.fallback is not None else None,
            on_retry=on_retry,
            on_fallback=on_fallback,
        )


def _model_name(message: AIMessage) -> str:
    name = (message.response_metadata or {}).get("model_name", "")
    # 응답 모델 이름에 날짜 접미사가 붙어 오므로 가격표 키와 맞추려고 앞부분만 비교한다.
    for known in ("gpt-4o-mini", "gpt-4.1-mini"):
        if name.startswith(known):
            return known
    return name
