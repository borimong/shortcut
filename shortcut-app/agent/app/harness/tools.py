"""MCP 도구 호출을 Harness 규칙(허용 목록, 승인, 반복 제한, 결과 길이, 오류 변환)으로 감쌉니다."""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from app.harness.guardrails import DESTRUCTIVE_TOOLS, as_untrusted, mask_value
from app.harness.recovery import PermanentError

if TYPE_CHECKING:
    from app.runtime import RunContext


class MissingToolError(PermanentError):
    """허용 목록의 도구가 MCP 서버에 없을 때 냅니다."""


_TOOL_ERROR = re.compile(r"\[(?P<code>[A-Z0-9_]+)\](?P<message>.*?)\(retryable=(?P<retryable>true|false)\)", re.S)


@dataclass
class ToolOutcome:
    """도구 한 번의 결과입니다. content는 모델에 넘길 문자열, data는 코드가 쓰는 원본입니다."""

    name: str
    ok: bool
    content: str
    data: Any = None
    error_code: str | None = None
    retryable: bool = False


class McpConnections:
    """MCP 서버마다 Streamable HTTP로 따로 연결합니다. 키가 도구 이름 접두어가 됩니다(business_, rag_, ops_).

    여러 서버를 설정 하나로 묶으면 한 서버가 꺼져 있어도 경고만 남기고 넘어가므로,
    연결 실패를 작업 재시도로 이어 가려고 서버마다 Client를 둔다.
    """

    def __init__(self, urls: dict[str, str], acting_user: str | None):
        headers = {"X-Acting-User": acting_user} if acting_user else {}
        self._urls = dict(urls)
        self._headers = headers
        self._stack = AsyncExitStack()
        self.clients: dict[str, Client] = {}

    async def __aenter__(self) -> dict[str, Client]:
        for prefix, url in self._urls.items():
            client = Client(StreamableHttpTransport(url, headers=self._headers))
            self.clients[prefix] = await self._stack.enter_async_context(client)
        return self.clients

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.aclose()


class ToolGateway:
    """도구 이름 앞에 서버 접두어(business_, rag_, ops_)를 붙여 하나의 목록처럼 다룹니다."""

    def __init__(self, clients: dict[str, Any], *, timeout_seconds: float, max_chars: int, max_same_calls: int):
        self._clients = clients
        self._timeout = timeout_seconds
        self._max_chars = max_chars
        self._max_same_calls = max_same_calls
        self._specs: dict[str, dict] | None = None
        # 실행팀 Agent가 Send로 동시에 처음 목록을 읽으면 먼저 들어온 쪽이 빈 dict를 넣은 채 기다리는 사이
        # 다른 쪽이 빈 목록을 보고 도구가 없다고 판단하므로 목록 채우기를 잠금으로 묶는다.
        self._specs_lock = asyncio.Lock()

    async def specs(self, allowed: list[str]) -> list[dict]:
        """허용된 도구만 OpenAI tool 형식으로 돌려줍니다. 모델은 이 설명을 읽고 도구를 고른다."""
        async with self._specs_lock:
            if self._specs is None:
                self._specs = await self._load_specs()
            # 목록은 처음 한 번 읽어 두므로, 에이전트보다 늦게 뜬 MCP 서버의 도구는 빠져 있을 수 있다. 한 번 다시 읽는다.
            if any(name not in self._specs for name in allowed):
                self._specs = await self._load_specs()
        missing = [name for name in allowed if name not in self._specs]
        if missing:
            # 다시 읽어도 없으면 설정 문제라 작업을 재시도해도 같은 오류가 난다.
            raise MissingToolError(f"MCP 도구 목록에 없는 도구: {', '.join(missing)}")
        return [self._specs[name] for name in allowed]

    async def _load_specs(self) -> dict[str, dict]:
        specs: dict[str, dict] = {}
        for prefix, client in self._clients.items():
            for tool in await client.list_tools():
                schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
                specs[f"{prefix}_{tool.name}"] = {
                    "type": "function",
                    "function": {"name": f"{prefix}_{tool.name}", "description": tool.description or "", "parameters": schema},
                }
        return specs

    async def call(
        self, ctx: RunContext, name: str, args: dict[str, Any], *, allowed: list[str], approved: bool = False
    ) -> ToolOutcome:
        """규칙을 통과한 호출만 MCP로 보내고, 실패는 예외 대신 오류 결과로 돌려줍니다."""
        if name not in allowed:
            return self._refuse(
                name, "TOOL_NOT_ALLOWED", f"이 단계에서 쓸 수 없는 도구입니다. 쓸 수 있는 도구: {', '.join(allowed)}"
            )
        if name in DESTRUCTIVE_TOOLS and not approved:
            return self._refuse(name, "APPROVAL_REQUIRED", "되돌릴 수 없는 도구는 필수 승인자 전원 승인 뒤에만 실행합니다.")

        signature = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        seen = ctx.counter["signatures"].get(signature, 0)
        if seen >= self._max_same_calls:
            return self._refuse(
                name, "REPEATED_CALL", "같은 도구를 같은 인자로 이미 여러 번 불렀습니다. 다른 도구나 다른 인자를 쓰세요."
            )
        ctx.counter["signatures"][signature] = seen + 1
        ctx.counter["tool_calls"] += 1

        prefix, _, tool_name = name.partition("_")
        agent = getattr(ctx, "agent", None)
        await ctx.events.publish("TOOL_START", {"tool": tool_name, "server": prefix, "agent": agent, "args": mask_value(args)})
        started = time.monotonic()
        outcome = await self._call_once(prefix, tool_name, name, args)
        # 연결 끊김이나 일시 오류는 같은 호출을 한 번 더 보내 보고, 인자 오류는 모델이 고치도록 그대로 돌려준다.
        if not outcome.ok and outcome.retryable:
            ctx.counter["retries"] += 1
            outcome = await self._call_once(prefix, tool_name, name, args)
        await ctx.events.publish(
            "TOOL_END",
            {
                "tool": tool_name,
                "agent": agent,
                "ok": outcome.ok,
                "ms": int((time.monotonic() - started) * 1000),
                "preview": outcome.content[:160] if outcome.ok else outcome.error_code,
            },
        )
        return outcome

    async def read_resource(self, prefix: str, uri: str) -> str:
        """Resource 원문을 읽습니다. 근거 패널에 보여 줄 조항 원문에 쓴다."""
        contents = await self._clients[prefix].read_resource(uri)
        return mask_value(contents[0].text)

    async def _call_once(self, prefix: str, tool_name: str, name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            result = await asyncio.wait_for(
                self._clients[prefix].call_tool(tool_name, args, raise_on_error=False), timeout=self._timeout
            )
        except TimeoutError:
            return ToolOutcome(
                name, False, f"[TOOL_TIMEOUT] {self._timeout:.0f}초 안에 응답이 없습니다.", None, "TOOL_TIMEOUT", True
            )
        except Exception as error:
            return ToolOutcome(name, False, f"[MCP_UNAVAILABLE] {error}", None, "MCP_UNAVAILABLE", True)

        if result.is_error:
            text = " ".join(getattr(block, "text", "") for block in result.content)
            match = _TOOL_ERROR.search(text)
            code = match.group("code") if match else "TOOL_ERROR"
            retryable = bool(match and match.group("retryable") == "true")
            return ToolOutcome(name, False, mask_value(text), None, code, retryable)

        data = result.structured_content if result.structured_content is not None else result.data
        # FastMCP는 dict가 아닌 반환값을 {"result": 값}으로 감싸므로 원래 모양으로 되돌린다.
        if isinstance(data, dict) and set(data) == {"result"}:
            data = data["result"]
        data = mask_value(data)
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + f"\n(결과가 길어 {len(text) - self._max_chars}자를 생략했습니다)"
        return ToolOutcome(name, True, as_untrusted(name, text), data)

    @staticmethod
    def _refuse(name: str, code: str, message: str) -> ToolOutcome:
        return ToolOutcome(name, False, f"[{code}] {message}", None, code, False)
