"""BackendError → 모델이 읽는 ToolError 메시지 (아키텍처 문서 6장 '오류 응답 → ToolError 변환').

원칙: 메시지에는 "무엇이 잘못됐는지"와 "다음에 무엇을 하면 되는지"를 함께 넣는다.
모델은 이 메시지만 보고 다시 호출할지, 다른 도구를 쓸지, 멈출지를 정한다.
맨 앞의 [CODE] 태그는 Agent Harness가 재시도 여부를 판단할 때 쓴다.
"""
from __future__ import annotations

from typing import Any

from .backend import BackendError


def _join(items: Any) -> str:
    if not items:
        return "없음"
    if isinstance(items, (list, tuple)):
        return ", ".join(_fmt(i) for i in items)
    return _fmt(items)


def _fmt(item: Any) -> str:
    if isinstance(item, dict):
        if "start" in item and "end" in item:
            prefix = f"{item['date']} " if "date" in item else ""
            return f"{prefix}{item['start']}~{item['end']}"
        return ", ".join(f"{k}={v}" for k, v in item.items())
    return str(item)


def to_tool_message(err: BackendError) -> str:
    d = err.details
    code = err.code
    tag = f"[{code}]" + ("[RETRYABLE]" if err.retryable else "")

    if code == "SCENE_NOT_FOUND":
        return f"{tag} {err.message}. 비슷한 씬: {_join(d.get('similar'))}. 이 중 맞는 ID로 다시 호출하라."
    if code in {"ACTOR_NOT_FOUND", "LOCATION_NOT_FOUND", "PERMIT_NOT_FOUND", "SCHEDULE_NOT_FOUND", "DRAFT_NOT_FOUND"}:
        return f"{tag} {err.message}. 사용할 수 있는 ID: {_join(d.get('available') or d.get('similar'))}."
    if code == "ACTOR_UNAVAILABLE":
        return (
            f"{tag} {err.message}. 가능한 시간대: {_join(d.get('available'))}. "
            "해당 씬을 가능한 시간대로 옮긴 초안을 다시 만들어라."
        )
    if code == "EQUIPMENT_CONFLICT":
        return (
            f"{tag} {err.message}. 비어 있는 시간대: {_join(d.get('freeSlots'))}. "
            f"대체 장비: {_join(d.get('alternatives'))}."
        )
    if code == "APPROVAL_REQUIRED":
        return (
            f"{tag} 감독 승인 기록이 없어 실행하지 않았다. 이 도구를 다시 호출하지 말고 "
            "초안을 저장한 뒤 승인 절차(approval_gate)로 넘어가라."
        )
    if code == "HARD_VIOLATION":
        violations = d.get("violations") or []
        lines = "; ".join(f"{v.get('type')}: {v.get('detail')} (힌트: {v.get('hint', '-')})" for v in violations)
        return (
            f"{tag} 하드 제약 위반 {len(violations)}건이 남아 확정할 수 없다. {lines}. "
            "초안을 고친 뒤 validate_schedule로 다시 검증하라."
        )
    if code == "FORBIDDEN":
        return f"{tag} 권한이 없다: {err.message}. 이 사용자로는 이 작업을 할 수 없으니 사용자에게 알려라."
    if code == "VALIDATION_ERROR":
        return f"{tag} 인자 형식이 잘못됐다: {err.message}. {_join(d.get('fields'))}"
    if err.retryable:
        return f"{tag} 일시적인 오류다({err.message}). 잠시 후 같은 인자로 다시 호출하라."
    return f"{tag} {err.message}"
