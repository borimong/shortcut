"""모델에 넘기는 데이터와 모델이 고른 행동을 제한하는 Guardrails입니다."""

from __future__ import annotations

import re
from typing import Any

# 매니저 연락처처럼 업무 데이터에 섞여 오는 개인정보는 모델 판단에 필요 없으므로 넘기기 전에 가린다.
_PHONE = re.compile(r"\b(01[016789])[-\s]?(\d{3,4})[-\s]?(\d{4})\b")
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_RESIDENT_NO = re.compile(r"\b(\d{6})[-\s]?([1-4])\d{6}\b")

# 되돌릴 수 없는 도구다. 사람 승인을 받은 노드만 approved=True로 부를 수 있다.
DESTRUCTIVE_TOOLS = frozenset({"business_commit_plan", "rag_delete_document"})
# 업무 데이터를 바꾸는 도구다. LLM이 고르는 노드의 허용 목록에는 넣지 않는다.
WRITE_TOOLS = DESTRUCTIVE_TOOLS | {"business_submit_proposal", "business_link_entity", "rag_index_document"}
# 실행 Agent가 가상 외부 서비스에 남기는 쓰기 도구다. 사람 승인으로 확정된 뒤에만 도는 실행팀의 허용 목록에만 넣는다.
OPS_WRITE_TOOLS = frozenset(
    {
        "ops_venue_hold",
        "ops_venue_confirm",
        "ops_venue_cancel",
        "ops_rental_book",
        "ops_rental_cancel",
        "ops_permit_apply",
        "ops_transport_book",
        "ops_transport_cancel",
        "ops_send_message",
        "ops_ledger_record",
    }
)


def mask_pii(text: str) -> str:
    """전화번호, 이메일, 주민등록번호를 뒤 네 자리나 첫 글자만 남기고 가립니다."""
    text = _PHONE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", text)
    text = _EMAIL.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
    return _RESIDENT_NO.sub(lambda m: f"{m.group(1)}-{m.group(2)}******", text)


def mask_value(value: Any) -> Any:
    """dict와 list 안의 문자열까지 재귀적으로 가립니다."""
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {key: mask_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    return value


def as_untrusted(tool_name: str, content: str) -> str:
    """도구 결과를 지시가 아닌 데이터로 읽도록 경계 태그로 감쌉니다."""
    # 규정 문서나 장소 설명 안에 명령처럼 보이는 문장이 있어도 시스템 프롬프트가 이 태그 안은 데이터라고 못 박는다.
    return f'<tool_result tool="{tool_name}">\n{content}\n</tool_result>'
