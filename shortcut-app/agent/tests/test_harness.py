"""Harness 구성 요소(Instructions, Tools, Agent Loop, Context, Guardrails, Recovery)를 요소마다 하나 이상 검증합니다."""

from __future__ import annotations

import asyncio
import re

import httpx
import openai
import pytest

from app.config import Limits
from app.harness.context import Section, count_tokens, fit_sections, summarize_loops
from app.harness.guardrails import mask_pii, mask_value
from app.harness.instructions import PROMPT_DIR, prompt_versions, render
from app.harness.limits import LOOP_LIMIT, TIME_LIMIT, TOOL_LIMIT, new_counter, stop_condition
from app.harness.recovery import ModelUnavailableError, call_with_recovery
from tests.fakes import make_context


def run(coro):
    return asyncio.run(coro)


def _status_error(status: int):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status, request=request)
    error_class = (
        openai.RateLimitError if status == 429 else openai.InternalServerError if status >= 500 else openai.BadRequestError
    )
    return error_class("error", response=response, body=None)


def test_every_prompt_renders_and_has_a_version():
    values = {name: "x" for name in re.findall(r"\$([a-z_]+)", "".join(p.read_text() for p in PROMPT_DIR.glob("*.md")))}
    for path in PROMPT_DIR.glob("*.md"):
        assert render(path.stem, **values)
    versions = prompt_versions()
    assert len(versions) == len(list(PROMPT_DIR.glob("*.md")))
    assert all(len(v) == 8 for v in versions.values())


def test_tool_not_in_allowlist_is_refused_without_calling_server():
    ctx, _, clients, _ = make_context()
    ctx.counter = new_counter()
    outcome = run(ctx.tools.call(ctx, "business_get_weather", {"shoot_day_id": 1}, allowed=["rag_search_regulation"]))
    assert outcome.error_code == "TOOL_NOT_ALLOWED"
    assert clients["business"].calls == []


def test_destructive_tool_needs_approval_flag():
    ctx, backend, _, _ = make_context()
    ctx.counter = new_counter()
    refused = run(
        ctx.tools.call(ctx, "business_commit_plan", {"proposal_id": 1, "data_version": 1}, allowed=["business_commit_plan"])
    )
    assert refused.error_code == "APPROVAL_REQUIRED"
    assert backend.commits == []
    allowed = run(
        ctx.tools.call(
            ctx, "business_commit_plan", {"proposal_id": 1, "data_version": 1}, allowed=["business_commit_plan"], approved=True
        )
    )
    assert allowed.ok


def test_same_call_more_than_three_times_is_refused():
    ctx, _, clients, _ = make_context()
    ctx.counter = new_counter()
    outcomes = [
        run(ctx.tools.call(ctx, "business_get_weather", {"shoot_day_id": 1}, allowed=["business_get_weather"])) for _ in range(4)
    ]
    assert [o.ok for o in outcomes] == [True, True, True, False]
    assert outcomes[-1].error_code == "REPEATED_CALL"
    assert len(clients["business"].calls) == 3


def test_tool_result_is_masked_truncated_and_marked_as_data():
    ctx, _, _, events = make_context()
    ctx.counter = new_counter()
    ctx.tools._max_chars = 120
    outcome = run(ctx.tools.call(ctx, "business_get_availability", {"shoot_day_id": 1}, allowed=["business_get_availability"]))
    assert "010-2481-7731" not in outcome.content
    assert outcome.content.startswith('<tool_result tool="business_get_availability">')
    assert "생략했습니다" in outcome.content
    assert [t for t, _ in events.events] == ["TOOL_START", "TOOL_END"]


def test_tool_error_text_is_parsed_into_code_and_retryable_flag():
    ctx, backend, _, _ = make_context()
    backend.commit_conflicts = 1
    ctx.counter = new_counter()
    outcome = run(
        ctx.tools.call(
            ctx, "business_commit_plan", {"proposal_id": 1, "data_version": 1}, allowed=["business_commit_plan"], approved=True
        )
    )
    assert outcome.error_code == "VERSION_CONFLICT"
    assert outcome.retryable is False
    assert ctx.counter["retries"] == 0


def test_stop_conditions_follow_limits():
    limits = Limits(max_loops=3, max_tool_calls=20, max_seconds=120)
    counter = new_counter()
    assert stop_condition(counter, limits) is None
    assert stop_condition({**counter, "loops": 4}, limits) == LOOP_LIMIT
    assert stop_condition({**counter, "tool_calls": 21}, limits) == TOOL_LIMIT
    assert stop_condition({**counter, "loop_elapsed_ms": 120_001}, limits) == TIME_LIMIT
    # 시간 한도는 루프마다 다시 센다. 거절이 여러 번 이어져 작업 전체 시간이 길어진 것만으로는 멈추지 않는다.
    assert stop_condition({**counter, "elapsed_ms": 300_000, "loop_elapsed_ms": 10_000}, limits) is None


def test_low_priority_sections_are_trimmed_first():
    sections = [Section("핵심", "선택한 후보 " * 20, 0), Section("참고", "비교 후보 설명 " * 2000, 3)]
    body = fit_sections(sections, budget=400)
    assert count_tokens(body) <= 450
    assert body.count("선택한 후보") == 20


def test_old_loops_are_summarized():
    lines = [f"루프 {i}: 후보 | 결과: 거절 {i}" for i in range(1, 4)]
    summary = summarize_loops(lines)
    assert summary.startswith("이전 2개 루프 요약: 거절 1; 거절 2")
    assert summary.endswith(lines[-1])


def test_pii_is_masked_recursively():
    assert mask_pii("매니저 010-2481-7731") == "매니저 010-****-7731"
    assert mask_pii("a.kim@example.com") == "a***@example.com"
    assert mask_value({"x": ["900101-1234567"]}) == {"x": ["900101-1******"]}


def test_retry_twice_then_fallback():
    attempts, retries, fallbacks = [], [], []

    async def primary():
        attempts.append(1)
        raise _status_error(429)

    async def fallback():
        return "fallback answer"

    async def no_sleep(_):
        return None

    result = run(
        call_with_recovery(
            primary, fallback, on_retry=lambda: retries.append(1), on_fallback=lambda: fallbacks.append(1), sleep=no_sleep
        )
    )
    assert result == "fallback answer"
    assert len(attempts) == 3
    assert len(retries) == 2 and len(fallbacks) == 1


def test_non_retryable_error_is_raised_immediately():
    attempts = []

    async def primary():
        attempts.append(1)
        raise _status_error(400)

    with pytest.raises(openai.BadRequestError):
        run(call_with_recovery(primary, None))
    assert len(attempts) == 1


def test_all_models_failing_raises_model_unavailable():
    async def failing():
        raise _status_error(503)

    async def no_sleep(_):
        return None

    with pytest.raises(ModelUnavailableError):
        run(call_with_recovery(failing, failing, sleep=no_sleep))


def test_tool_specs_load_once_when_parallel_agents_ask_at_the_same_time():
    """실행팀 Agent가 Send로 동시에 처음 도구 목록을 읽어도 빈 목록을 보지 않아야 한다."""
    import asyncio as _asyncio
    from types import SimpleNamespace as _NS

    from app.harness.tools import ToolGateway as _Gateway

    class SlowClient:
        calls = 0

        async def list_tools(self):
            SlowClient.calls += 1
            await _asyncio.sleep(0.05)
            return [
                _NS(name="venue_check", description="", input_schema={}),
                _NS(name="rental_quote", description="", input_schema={}),
            ]

    gateway = _Gateway({"ops": SlowClient()}, timeout_seconds=1, max_chars=1000, max_same_calls=3)

    async def scenario():
        return await _asyncio.gather(gateway.specs(["ops_venue_check"]), gateway.specs(["ops_rental_quote"]))

    first, second = _asyncio.run(scenario())
    assert first[0]["function"]["name"] == "ops_venue_check"
    assert second[0]["function"]["name"] == "ops_rental_quote"
    assert SlowClient.calls == 1


def test_tool_specs_reload_once_when_a_server_started_late():
    """에이전트보다 늦게 뜬 MCP 서버의 도구는 목록을 한 번 다시 읽어 찾고, 그래도 없으면 재시도하지 않을 오류를 낸다."""
    from types import SimpleNamespace as _NS

    from app.harness.recovery import PermanentError
    from app.harness.tools import ToolGateway as _Gateway

    class LateClient:
        calls = 0

        async def list_tools(self):
            LateClient.calls += 1
            names = ["venue_check"] if LateClient.calls == 1 else ["venue_check", "rental_quote"]
            return [_NS(name=n, description="", input_schema={}) for n in names]

    gateway = _Gateway({"ops": LateClient()}, timeout_seconds=1, max_chars=1000, max_same_calls=3)
    assert run(gateway.specs(["ops_rental_quote"]))[0]["function"]["name"] == "ops_rental_quote"
    assert LateClient.calls == 2
    with pytest.raises(PermanentError):
        run(gateway.specs(["ops_ledger_record"]))


def test_structured_output_is_asked_once_more_when_parsing_fails():
    """모델이 필수 필드를 빠뜨려 해석에 실패하면 같은 요청을 한 번 더 보냅니다."""
    from types import SimpleNamespace as _NS

    from app.harness.model import ModelGateway

    gateway = ModelGateway(primary=None, fallback=None)
    raw = _NS(usage_metadata=None, response_metadata={})
    answers = iter(
        [
            {"raw": raw, "parsed": None, "parsing_error": "thought.decision Field required"},
            {"raw": raw, "parsed": {"ok": True}, "parsing_error": None},
        ]
    )

    async def fake_recover(ctx, call):
        return next(answers)

    gateway._recover = fake_recover
    ctx, _, _, _ = make_context()
    assert run(gateway.structured(ctx, [], dict)) == {"ok": True}
