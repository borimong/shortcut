"""backend 내부 API(`/internal/ops/**`) 호출 클라이언트.

ops-mcp는 가상 외부 서비스(아워플레이스, 렌탈사, 허가 기관, 차량 업체, 메시지 발송, 장부)의 규칙을 갖지 않는다.
business-mcp의 backend.py와 같은 일을 한다.
1. `X-Internal-Token`과, Agent가 MCP 요청에 실어 보낸 `X-Acting-User`를 붙여 backend를 부른다.
2. 성공 응답 JSON을 그대로 돌려준다.
3. 실패 응답 `{code, message, ...}`와 연결 실패를 BackendError로 바꾼다. 모델용 문장은 errors.py가 만든다.

경로와 본문은 shortcut-app/backend의 `web/internal/InternalOpsController.java`를 따른다.
"""

from __future__ import annotations

import os
from typing import Any

try:  # httpx와 그 후속 패키지 httpx2 중 설치된 쪽을 쓴다
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

# 내부 API 한 번이 길어지면 Agent 작업 한도(120초)를 혼자 다 쓰게 되므로 10초에서 끊는다.
REQUEST_TIMEOUT_SECONDS = 10.0
ACTING_USER_HEADER = "X-Acting-User"


class BackendError(Exception):
    """backend 호출 실패. status 0은 응답을 받지 못한 경우(연결 실패, 시간 초과)다."""

    def __init__(self, status: int, code: str, message: str, body: dict[str, Any] | None = None):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.body = body or {}

    @property
    def retryable(self) -> bool:
        """같은 인자로 다시 보내면 성공할 수 있는가. 4xx는 인자나 상태를 바꿔야 하므로 아니다."""
        return self.status == 0 or self.status == 429 or self.status >= 500


def acting_user() -> str | None:
    """MCP 요청 헤더의 작업 요청자를 읽는다. HTTP 요청 밖(인메모리 테스트)에서는 None."""
    try:
        from fastmcp.server.dependencies import get_http_headers
    except ImportError:  # pragma: no cover
        return None
    try:
        return get_http_headers().get("x-acting-user") or None
    except RuntimeError:
        return None


class BackendClient:
    """backend 내부 API 호출기. 테스트에서는 transport에 httpx.MockTransport를 넘긴다."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        transport: Any = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ):
        self.base_url = (
            base_url
            or os.getenv("BACKEND_INTERNAL_URL")
            or os.getenv("BACKEND_URL")  # 예전 이름
            or "http://localhost:8080"
        ).rstrip("/")
        self.token = token if token is not None else os.getenv("INTERNAL_TOKEN", "local-internal-token")
        self.transport = transport
        self.timeout = timeout

    async def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        headers = {"X-Internal-Token": self.token}
        user = acting_user()
        if user:
            headers[ACTING_USER_HEADER] = user
        params = {k: v for k, v in (params or {}).items() if v is not None}

        try:
            async with httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=self.timeout) as client:
                resp = await client.request(method, path, headers=headers, params=params or None, json=json)
        except httpx.TimeoutException as exc:
            raise BackendError(0, "BACKEND_TIMEOUT", "업무 API 응답이 늦습니다") from exc
        except httpx.TransportError as exc:
            raise BackendError(0, "BACKEND_UNAVAILABLE", "업무 API에 연결할 수 없습니다") from exc

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            raise BackendError(
                resp.status_code,
                body.get("code") or f"HTTP_{resp.status_code}",
                body.get("message") or resp.reason_phrase or "오류 응답",
                body,
            )
        if resp.status_code == 204 or not resp.content:
            return {"ok": True}
        return resp.json()
