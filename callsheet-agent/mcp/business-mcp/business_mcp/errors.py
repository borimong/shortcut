"""BackendError → 모델이 읽는 ToolError 메시지 (계약 rc2 README 4장 '오류 details 규칙').

원칙: 메시지에 "무엇이 잘못됐는지"와 "다음에 무엇을 하면 되는지"를 함께 넣는다.
맨 앞의 [CODE] 태그로 Agent Harness가 처리를 나눈다.
- [RETRYABLE]          같은 인자로 재시도
- [APPROVAL_REQUIRED]  재시도하지 말고 승인 대기(approval_gate)로
- [STALE_PLAN]         데이터가 바뀜 → 1/2/3안 재평가(evaluate_plans)부터 다시
- [HARD_VIOLATION]     위반 내용을 State에 기록하고 다른 조합으로 다시 구성
"""
from __future__ import annotations

from typing import Any

from .backend import BackendError


def _join(items: Any) -> str:
    if not items:
        return "없음"
    if isinstance(items, (list, tuple)):
        return ", ".join(str(i) for i in items)
    return str(items)


def to_tool_message(err: BackendError) -> str:
    d, code = err.details, err.code
    tag = f"[{code}]" + ("[RETRYABLE]" if err.retryable else "")

    if code in {"ENTITY_NOT_FOUND", "BLOCK_NOT_FOUND", "PLAN_NOT_FOUND", "LOCATION_NOT_FOUND", "PACKAGE_NOT_FOUND"}:
        extra = f" 엔티티 유형: {_join(d.get('entityTypes'))}." if d.get("entityTypes") else ""
        return f"{tag} {err.message}. 사용할 수 있는 ID: {_join(d.get('available'))}.{extra} 맞는 ID로 다시 호출하라."
    if code == "CANDIDATE_NOT_FOUND":
        return f"{tag} {err.message}. build_schedule로 후보를 다시 만든 뒤 받은 planHash를 써라."
    if code == "APPROVAL_REQUIRED":
        return (f"{tag} 필수 승인자 전원의 승인이 없어 실행하지 않았다(계획안 상태 {d.get('planStatus', '-')}, "
                f"대기 역할: {_join(d.get('pendingRoles'))}). 이 도구를 다시 호출하지 말고 승인 대기(approval_gate)로 가라.")
    if code == "STALE_PLAN":
        return (f"{tag} {err.message} (현재 데이터 버전 {d.get('currentDataVersion', '-')}). "
                "같은 후보로 재시도하지 말고 evaluate_plans로 최신 데이터에서 다시 평가하라.")
    if code == "HARD_VIOLATION":
        vs = d.get("violations") or []
        lines = "; ".join(f"{v.get('code')}: {v.get('detail')} (힌트: {v.get('hint', '-')})" for v in vs)
        return f"{tag} 하드 제약 위반 {len(vs)}건: {lines}. 이 조합은 버리고 evaluate_plans 결과의 다른 조합을 써라."
    if code == "BOOKING_NOT_NEEDED":
        return f"{tag} {err.message}. 예약 요청 없이 commit_plan으로 넘어가라."
    if code == "FORBIDDEN":
        return f"{tag} 권한이 없다: {err.message} (허용 역할: {_join(d.get('allowedRoles'))}). 사용자에게 알려라."
    if code == "VALIDATION_ERROR":
        return f"{tag} 인자 형식이 잘못됐다: {err.message}. 확인할 필드: {_join(d.get('fields'))}."
    if err.retryable:
        return f"{tag} 일시적인 오류다({err.message}). 잠시 후 같은 인자로 다시 호출하라."
    return f"{tag} {err.message}"
