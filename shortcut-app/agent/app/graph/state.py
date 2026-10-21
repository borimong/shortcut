"""재계획 그래프와 질의응답 그래프의 State 구조입니다. 체크포인트에 그대로 저장됩니다."""

from __future__ import annotations

from typing import Any, TypedDict

# 하드 제약 범주다. 노션 설계의 5개(계약서, 스케줄, 규제/법, 예산, 촬영 금지 구역)에
# 천재지변(재난 문자)과 강수확률 기준 날씨를 더했다.
HARD_CONSTRAINTS = ("CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER")

DEFAULT_WEIGHTS = {"location": 0.25, "equipment": 0.15, "weather": 0.20, "budget": 0.15, "time": 0.10, "distance": 0.15}


class ReplanState(TypedDict, total=False):
    """변경 이벤트 하나를 처리하는 동안의 상태입니다."""

    task_id: int
    thread_id: str
    shoot_day_id: int
    # 변경 이벤트와 요청자. {id, type, detail, instruction, requested_by}
    event: dict[str, Any]
    # 1/2/3안과 현재 확정안, 업무 데이터 버전
    plan_set: dict[str, Any]
    data_version: int
    # 과거 거절 기록(장기 메모리)에서 읽은 참고 사항
    memory_notes: list[str]
    # 온톨로지로 찾은 영향 엔티티 묶음
    impacted_entities: dict[str, Any]
    # 날씨, 재난 문자, 가용 자원 조회 결과
    conditions: dict[str, Any]
    # 하드 제약 범주별 요약과 근거 chunk ID
    hard_constraints: list[dict[str, Any]]
    # chunk_id -> 검색된 조항
    evidence: dict[str, dict[str, Any]]
    missing_info: list[str]
    info_retries: int
    # 최적화 가중치와 조정 이유
    weights: dict[str, float]
    weight_rationale: str
    # 업무 규칙 엔진의 평가 결과
    candidates: list[dict[str, Any]]
    feasible_count: int
    # 이번 루프의 최적안 1개
    selected_plan: dict[str, Any] | None
    # 검증 게이트 위반 기록과 다시 만들지 않을 후보 해시
    violations: list[dict[str, Any]]
    failed_hashes: list[str]
    # 검증 게이트 판정. PASS, VIOLATION, STALE
    gate_result: str
    # 거절 사유에서 만든 추가 제약
    extra_constraints: list[dict[str, Any]]
    # 승인 요청과 결과. {proposal_id, version_no, required, decision, role, reason}
    approvals: dict[str, Any]
    callsheet_version_no: int | None
    # 루프별 한 줄 기록. 오래된 루프는 Context 단계에서 요약된다
    loop_summaries: list[str]
    # 루프, 도구 호출, 경과 시간, 토큰, 비용, 재시도 집계
    loop_counter: dict[str, Any]
    stop_condition: str | None
    # 마지막 거절. {role, reason, issues, hash, location_id, equipment_ids, start, end}
    last_rejection: dict[str, Any] | None
    # 이 작업에서 거절된 안 전부. 문제로 지목된 요소가 같은 후보를 다시 올리지 않으려고 쌓아 둔다
    rejected_plans: list[dict[str, Any]]
    # 거절된 안과 겹쳐 거른 뒤 남은 후보가 없으면, 거른 후보를 빼고 엔진에 다시 평가를 맡긴다
    repeat_filtered: bool
    # 장소 문제로 거절되면 남은 1/2/3안을 고르기 전에 4안 대체 장소부터 찾아 후보를 넓힌다
    widen_search: bool
    # 4안 구성을 이미 시도했는지와 등록한 대체 장소
    alternatives_tried: bool
    # 자체 검토. 이번 루프의 회차, 회차별 점수와 피드백, 가장 점수가 높았던 안, 다음 회차에 반영할 피드백
    review_round: int
    review_history: list[dict[str, Any]]
    best_review: dict[str, Any] | None
    review_feedback: list[str]
    review_skipped: list[str]
    # 검증 게이트를 통과한 후보 해시. 설명만 고친 회차는 다시 검증하지 않는다
    validated_hash: str | None
    # 자체 검토 결과에 따라 갈 다음 노드와, 승인 요청에 함께 보낼 최종 검토 결과
    review_next: str
    review_result: dict[str, Any] | None
    alternatives: list[dict[str, Any]]
    suggestions: list[dict[str, Any]]
    result: dict[str, Any]


class QaState(TypedDict, total=False):
    """근거 질문 하나를 처리하는 동안의 상태입니다."""

    task_id: int
    question: str
    proposal_id: int | None
    tool_results: list[dict[str, Any]]
    evidence: dict[str, dict[str, Any]]
    answer: str
    loop_counter: dict[str, Any]
