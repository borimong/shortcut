"""backend `/internal/**` 호출 클라이언트 (아키텍처 문서 6장, 계약 3).

business-mcp는 업무 규칙을 갖지 않는다. 이 모듈은 다음 세 가지만 한다.
1. 사용자 컨텍스트(ctx)를 X-* 헤더로 바꿔 backend를 호출한다.
2. 성공 응답 JSON을 그대로 돌려준다.
3. 실패 응답 {code, message, details}를 BackendError로 바꾼다.
"""
from __future__ import annotations

import os
from typing import Any

try:  # httpx와 그 후속 패키지 httpx2 중 설치된 쪽을 쓴다
    import httpx
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore[no-redef]

# Agent가 큐 메시지의 user와 taskId로 채워 넘기는 키 (문서 5장, 6장)
REQUIRED_CTX_KEYS = ("id", "role", "productionId", "taskId")


class BackendError(Exception):
    """backend가 돌려준 오류. code는 문서 6장 '오류 응답' 표의 값이다."""

    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}

    @property
    def retryable(self) -> bool:
        """같은 인자로 다시 호출하면 성공할 수 있는 일시 오류인가."""
        return self.status >= 500 or self.code in {"INTERNAL", "BACKEND_UNAVAILABLE"}


def ctx_headers(ctx: dict[str, Any]) -> dict[str, str]:
    """ctx를 backend가 읽는 헤더로 바꾼다. 빠진 키가 있으면 바로 실패시킨다."""
    if not isinstance(ctx, dict):
        raise ValueError("ctx가 없다. Agent가 도구 호출 시 사용자 컨텍스트를 주입해야 한다.")
    missing = [k for k in REQUIRED_CTX_KEYS if ctx.get(k) in (None, "")]
    if missing:
        raise ValueError(f"ctx에 {', '.join(missing)} 값이 없다. 필요한 키: {', '.join(REQUIRED_CTX_KEYS)}")
    return {
        "X-User-Id": str(ctx["id"]),
        "X-User-Role": str(ctx["role"]),
        "X-Production-Id": str(ctx["productionId"]),
        "X-Task-Id": str(ctx["taskId"]),
    }


class BackendClient:
    """backend `/internal/**` 호출기.

    테스트에서는 transport에 ASGI/Mock transport를 넘겨 실제 서버 없이 호출한다.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        transport: Any = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.environ.get("BACKEND_URL", "http://backend:8080")).rstrip("/")
        self.token = token if token is not None else os.environ.get("INTERNAL_TOKEN", "dev-internal-token")
        self.transport = transport
        self.timeout = timeout

    async def request(
        self,
        method: str,
        path: str,
        ctx: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"X-Internal-Token": self.token, **ctx_headers(ctx)}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        params = {k: v for k, v in (params or {}).items() if v is not None}

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, transport=self.transport, timeout=self.timeout
            ) as client:
                resp = await client.request(method, path, headers=headers, params=params, json=json)
        except httpx.HTTPError as exc:  # 연결 실패, 타임아웃
            raise BackendError(503, "BACKEND_UNAVAILABLE", f"backend에 연결하지 못했다 ({type(exc).__name__})") from exc

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            raise BackendError(
                resp.status_code,
                body.get("code", "INTERNAL" if resp.status_code >= 500 else "HTTP_ERROR"),
                body.get("message", resp.text[:200] or "오류 응답"),
                body.get("details"),
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()
