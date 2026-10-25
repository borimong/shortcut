"""BackendError → 모델이 읽는 ToolError 문장.

형식은 business-mcp와 같은 `[CODE] 무엇이 잘못됐는지. 다음에 할 일 (retryable=true|false)`로 고정한다.
Agent Harness(shortcut-app/agent/app/harness/tools.py)가 정규식으로 CODE와 retryable을 읽어
재시도 여부를 정하므로 이 형식을 바꾸면 Agent도 함께 고쳐야 한다.
코드 목록은 backend OpsService와 GlobalExceptionHandler에서 가져왔다.
"""

from __future__ import annotations

from .backend import BackendError

# code → 모델이 다음에 할 일
HINTS: dict[str, str] = {
    "VENUE_CONFLICT": "같은 시간대에 다른 예약이 있어 가예약할 수 없습니다. 다른 시간이나 장소로 바꾸지 말고 실패로 보고하세요.",
    "RESERVATION_NOT_FOUND": "venue_check 결과의 reservations나 venue_hold 결과의 reservationId를 쓰세요.",
    "BOOKING_NOT_FOUND": "rental_quote나 transport_quote 결과의 bookings, 또는 예약 결과의 bookingId를 쓰세요.",
    "PERMIT_NOT_FOUND": "permit_apply 결과나 permit_check_requirement 결과의 permits에 있는 permitId를 쓰세요.",
    "INVALID_STATE": "이미 취소되었거나 상태가 맞지 않는 예약입니다. 조회 도구로 현재 상태를 확인하고 같은 호출을 반복하지 마세요.",
    "UNKNOWN_LOCATION": "작업 지시서에 적힌 확정 장소 ID를 쓰세요.",
    "UNKNOWN_EQUIPMENT": "작업 지시서에 적힌 확정 장비 ID를 쓰세요.",
    "SHOOT_DAY_NOT_FOUND": "작업 지시서의 촬영일 ID를 쓰세요.",
    "VALIDATION_FAILED": "인자 값을 고쳐 다시 부르세요. 장부는 account와 ref_type이 맞아야 합니다(CANCEL_FEE는 어느 ref_type이든 가능).",
    "BAD_REQUEST": "인자 형식을 고쳐 다시 부르세요.",
    "FORBIDDEN": "권한이 없는 작업입니다. 실패로 보고하세요.",
    "BACKEND_TIMEOUT": "잠시 뒤 같은 인자로 다시 시도할 수 있습니다.",
    "BACKEND_UNAVAILABLE": "잠시 뒤 같은 인자로 다시 시도할 수 있습니다.",
}


def format_error(code: str, message: str, retryable: bool) -> str:
    return f"[{code}] {message} (retryable={'true' if retryable else 'false'})"


def to_tool_message(err: BackendError) -> str:
    message = err.message.rstrip(". ") + "."
    hint = HINTS.get(err.code)
    if hint is None and err.retryable:
        hint = "잠시 뒤 같은 인자로 다시 시도할 수 있습니다."
    if hint:
        message += f" {hint}"
    return format_error(err.code, message, err.retryable)
