"""BackendError → 모델이 읽는 ToolError 문장.

형식은 `[CODE] 무엇이 잘못됐는지. 다음에 할 일 (retryable=true|false)`로 고정한다.
Agent Harness(shortcut-app/agent/app/harness/tools.py)가 정규식으로 CODE와 retryable을 읽어
재시도 여부를 정하므로 이 형식을 바꾸면 Agent도 함께 고쳐야 한다.
코드 목록은 backend의 ApiException·PlanRuleException·GlobalExceptionHandler에서 가져왔다.
"""
from __future__ import annotations

from .backend import BackendError

NODE_ID_HINT = "노드 ID는 TYPE:키 형식입니다. 예: SCENE:S12, ACTOR:1, LOCATION:2, BLOCK:1-PM, SHOOT_DAY:1, CONTRACT:contract-actor-a-v3."

# code → 모델이 다음에 할 일
HINTS: dict[str, str] = {
    "NODE_NOT_FOUND": NODE_ID_HINT,
    "INVALID_DEPTH": "depth는 1~3입니다.",
    "EDGE_EXISTS": "이미 같은 관계가 있으므로 다시 추가하지 않아도 됩니다.",
    "SHOOT_DAY_NOT_FOUND": "촬영일 ID를 확인하세요. 시연 데이터의 촬영일은 1입니다.",
    "PROPOSAL_NOT_FOUND": "submit_proposal 결과의 변경안 ID를 쓰세요.",
    "EXTERNAL_LOCATION_NOT_FOUND": "search_locations 결과의 id만 등록할 수 있습니다.",
    "VERSION_CONFLICT": "그 사이 업무 데이터가 바뀌었습니다. 같은 인자로 다시 부르지 말고 evaluate_plans부터 최신 데이터로 다시 평가하세요.",
    "NOT_APPROVED": "필수 승인자 전원의 승인이 아직 없습니다. 다시 부르지 말고 승인 결과를 기다리세요.",
    "PROPOSAL_NOT_PENDING": "이미 처리된 변경안입니다. get_proposal로 상태를 확인하세요.",
    "PLAN_INVALID": "이 후보는 버리고 evaluate_plans 결과의 다른 실행 가능 후보를 쓰세요.",
    "UNKNOWN_LOCATION": "get_plan_set이나 evaluate_plans 결과에 있는 장소 ID를 쓰세요.",
    "UNKNOWN_EQUIPMENT": "get_plan_set이나 evaluate_plans 결과에 있는 장비 ID를 쓰세요.",
    "UNKNOWN_CONSTRAINT": "추가 제약 type은 EXCLUDE_LOCATION, EXCLUDE_LOCATION_TIME, EXCLUDE_EQUIPMENT, MAX_EXTRA_COST, REQUIRE_INDOOR, LATEST_END, EXCLUDE_TIME 중 하나입니다.",
    "INVALID_CONSTRAINT": "제약 종류에 필요한 값(location_id, equipment_id, from_time/to_time, time, amount)을 채우세요.",
    "INVALID_WEIGHTS": "가중치는 0 이상이고 합이 0보다 커야 합니다. 키: location, equipment, weather, budget, time, distance.",
    "INVALID_TIME": "시작 시각이 종료 시각보다 빨라야 합니다(HH:mm).",
    "INVALID_SCENE_ORDER": "scene_order에는 오후 블록 씬 코드를 한 번씩 모두 넣거나, 비워서 서버가 고르게 하세요.",
    "VALIDATION_FAILED": "인자 값을 고쳐 다시 부르세요.",
    "BAD_REQUEST": "인자 형식을 고쳐 다시 부르세요.",
    "FORBIDDEN": "권한이 없는 작업입니다. 사용자에게 알리세요.",
    "BACKEND_TIMEOUT": "잠시 뒤 같은 인자로 다시 시도할 수 있습니다.",
    "BACKEND_UNAVAILABLE": "잠시 뒤 같은 인자로 다시 시도할 수 있습니다.",
}


def format_error(code: str, message: str, retryable: bool) -> str:
    return f"[{code}] {message} (retryable={'true' if retryable else 'false'})"


def to_tool_message(err: BackendError) -> str:
    message = err.message.rstrip(". ") + "."
    violations = err.body.get("violations") or []
    if violations:
        codes = ", ".join(str(v.get("code", "")) for v in violations if isinstance(v, dict))
        message += f" 위반: {codes}."
    hint = HINTS.get(err.code)
    if hint is None and err.retryable:
        hint = "잠시 뒤 같은 인자로 다시 시도할 수 있습니다."
    if hint:
        message += f" {hint}"
    return format_error(err.code, message, err.retryable)
