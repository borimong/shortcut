"""LLM 판단 결과를 코드가 검사할 수 있도록 받는 구조화 응답 스키마입니다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HardConstraint = Literal["CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER"]
ExecAgent = Literal["venue", "rental", "permit", "transport", "contact", "ledger"]


THOUGHT_FIELD = "생각 기록. 다른 필드보다 먼저 채웁니다. observation(본 사실과 숫자), decision(정한 것), reason(이유)"


class Thought(BaseModel):
    """판단 노드가 남기는 생각 기록입니다. 화면의 생각 기록 탭에 그대로 보이고, 사용자가 이 단위로 수정을 요청합니다."""

    observation: str = Field(description="무엇을 봤는지. 판단에 쓴 사실과 숫자를 한두 문장으로")
    decision: str = Field(description="무엇을 정했는지 한 문장으로")
    reason: str = Field(description="왜 그렇게 정했는지 한두 문장으로")


class ImpactedEntity(BaseModel):
    node_id: str = Field(description="온톨로지 노드 ID, 예: ACTOR:1")
    label: str
    why: str = Field(description="이번 변경으로 영향을 받는 이유 한 문장")


class ImpactSummary(BaseModel):
    """영향 분석 결과입니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    focus_nodes: list[str] = Field(description="변경이 직접 걸린 노드 ID")
    impacted: list[ImpactedEntity]
    risks: list[str] = Field(description="재계획 때 주의할 위험, 한 문장씩")


class ConstraintFinding(BaseModel):
    constraint: HardConstraint
    summary: str = Field(description="이번 재계획에 적용할 조건을 한두 문장으로")
    evidence_ids: list[str] = Field(description="검색 결과의 chunk_id만 인용")


class ConstraintSet(BaseModel):
    """하드 제약 범주별 적용 조건과 근거입니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    findings: list[ConstraintFinding]


class WeightAdjustment(BaseModel):
    """감독 지시를 반영한 최적화 가중치입니다. 합은 코드가 1로 맞춘다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    location: float = Field(ge=0, le=1)
    equipment: float = Field(ge=0, le=1)
    weather: float = Field(ge=0, le=1)
    budget: float = Field(ge=0, le=1)
    time: float = Field(ge=0, le=1)
    distance: float = Field(ge=0, le=1)
    rationale: str


class ChecklistEntry(BaseModel):
    constraint: HardConstraint
    status: Literal["PASS", "WARN"]
    note: str
    evidence_ids: list[str]


class PlanExplanation(BaseModel):
    """최적안 설명과 하드 제약 준수 체크리스트입니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    explanation: str = Field(description="승인자가 읽을 설명. 무엇이 왜 바뀌었는지 5문장 이내")
    checklist: list[ChecklistEntry]
    unresolved: list[str] = Field(description="아직 확정되지 않아 사람이 확인할 항목")
    needs_more_info: bool = Field(description="근거가 부족해 규정을 더 찾아야 하면 true")
    missing: list[HardConstraint] = Field(default_factory=list, description="근거가 부족한 제약 범주")


class ConstraintItem(BaseModel):
    """다음 루프에서 지킬 추가 제약 하나입니다."""

    type: Literal[
        "EXCLUDE_LOCATION",
        "EXCLUDE_LOCATION_TIME",
        "EXCLUDE_TIME",
        "EXCLUDE_EQUIPMENT",
        "MAX_EXTRA_COST",
        "REQUIRE_INDOOR",
        "LATEST_END",
    ]
    location_id: int | None = None
    equipment_id: int | None = None
    from_time: str | None = Field(default=None, description="HH:mm")
    to_time: str | None = Field(default=None, description="HH:mm")
    time: str | None = Field(default=None, description="HH:mm, LATEST_END일 때")
    amount: int | None = Field(default=None, description="원, MAX_EXTRA_COST일 때")


class RejectionPlan(BaseModel):
    """거절 사유를 보완하도록 바꾼 추가 제약 묶음입니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    constraints: list[ConstraintItem] = Field(min_length=1, max_length=3)
    summary: str = Field(description="무엇을 바꿔 사유를 보완할지 한 문장으로")


class AlternativeKeywords(BaseModel):
    """4안 탐색에 쓸 검색 조건입니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    keywords: list[str] = Field(min_length=1, max_length=5)
    max_distance_km: float = Field(gt=0, le=100)


class QuotedCheck(BaseModel):
    found: bool
    quote: str = Field(description="found가 true면 판단 근거가 된 설명 속 구절을 고치지 말고 그대로 옮김, false면 빈 문자열")


class ReviewChecks(BaseModel):
    """자체 검토에서 모델이 답하는 점검 질문입니다. 질문 문장은 상황에 맞게 코드가 프롬프트에 적는다.
    점수와 통과 여부는 코드가 계산하고, 인용이 설명에 실제로 없으면 그 답을 아니오로 본다."""

    change: QuotedCheck = Field(description="점검 질문 change에 대한 답")
    reason: QuotedCheck = Field(description="점검 질문 reason에 대한 답")
    responds: QuotedCheck = Field(description="점검 질문 responds에 대한 답")
    rejected_element: QuotedCheck = Field(description="점검 질문 rejected_element에 대한 답")
    cost_reason: QuotedCheck = Field(description="점검 질문 cost_reason에 대한 답")


class CandidateChoice(BaseModel):
    """사용자 수정 요청이 있을 때 실행 가능한 상위 후보 가운데 하나를 고릅니다. 실행 가능 여부는 엔진이 이미 판정했습니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    chosen_hash: str = Field(description="고른 후보의 hash. 목록에 있는 값만")


class ExecOrder(BaseModel):
    """supervisor가 실행 Agent 하나에게 주는 작업 지시서입니다."""

    agent: ExecAgent
    goal: str = Field(description="이 Agent가 끝내야 할 일 한 문장")
    constraints: list[str] = Field(default_factory=list, description="지켜야 할 조건. 예: 확정 시간대 밖으로 예약하지 않음")


class SupervisorDecision(BaseModel):
    """이번 단계에 보낼 실행 Agent와 지시서입니다. 단계 순서와 후보 Agent는 코드가 정하고, 누구를 보낼지만 고릅니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    orders: list[ExecOrder] = Field(description="이번 단계 후보 가운데 실제로 보낼 Agent의 지시서. 필요 없으면 빼도 됩니다")


class ExecutionNote(BaseModel):
    """실행 Agent의 보고입니다. 성공 여부와 예약 번호 같은 결과물은 코드가 도구 결과에서 직접 읽고, 여기에는 사람이 읽을 요약만 씁니다."""

    thought: Thought | None = Field(default=None, description=THOUGHT_FIELD)
    summary: str = Field(description="무엇을 했고 결과가 어떤지 한두 문장. 번호와 시각은 도구 결과에 있는 값만")
    needs_human: bool = Field(description="다시 시켜도 해결되지 않아 사람이 처리해야 하면 true. 예: 허가 반려, 예약 불가")
