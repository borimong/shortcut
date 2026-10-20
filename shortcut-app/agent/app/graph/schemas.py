"""LLM 판단 결과를 코드가 검사할 수 있도록 받는 구조화 응답 스키마입니다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HardConstraint = Literal["CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER"]


class ImpactedEntity(BaseModel):
    node_id: str = Field(description="온톨로지 노드 ID, 예: ACTOR:1")
    label: str
    why: str = Field(description="이번 변경으로 영향을 받는 이유 한 문장")


class ImpactSummary(BaseModel):
    """영향 분석 결과입니다."""

    focus_nodes: list[str] = Field(description="변경이 직접 걸린 노드 ID")
    impacted: list[ImpactedEntity]
    risks: list[str] = Field(description="재계획 때 주의할 위험, 한 문장씩")


class ConstraintFinding(BaseModel):
    constraint: HardConstraint
    summary: str = Field(description="이번 재계획에 적용할 조건을 한두 문장으로")
    evidence_ids: list[str] = Field(description="검색 결과의 chunk_id만 인용")


class ConstraintSet(BaseModel):
    """하드 제약 범주별 적용 조건과 근거입니다."""

    findings: list[ConstraintFinding]


class WeightAdjustment(BaseModel):
    """감독 지시를 반영한 최적화 가중치입니다. 합은 코드가 1로 맞춘다."""

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

    constraints: list[ConstraintItem] = Field(min_length=1, max_length=3)
    summary: str = Field(description="무엇을 바꿔 사유를 보완할지 한 문장으로")


class AlternativeKeywords(BaseModel):
    """4안 탐색에 쓸 검색 조건입니다."""

    keywords: list[str] = Field(min_length=1, max_length=5)
    max_distance_km: float = Field(gt=0, le=100)


class PlanReview(BaseModel):
    """승인 요청 전에 승인자 입장에서 매기는 자체 검토 점수입니다. 합계는 코드가 더한다."""

    evidence: int = Field(ge=0, le=20, description="하드 제약마다 원문 근거가 붙어 있고 WARN이 적은가")
    rejection: int = Field(ge=0, le=20, description="앞선 거절 사유를 보완했는가. 거절이 없었으면 변경 이벤트에 맞게 대응했는가")
    optimization: int = Field(ge=0, le=20, description="비용, 이동, 날씨, 시간의 균형이 합리적인가")
    explanation: int = Field(ge=0, le=20, description="무엇이 왜 바뀌었는지 숫자와 근거로 구체적으로 설명했는가")
    risk: int = Field(ge=0, le=20, description="미확정 항목과 실행 위험이 관리 가능한가")
    feedback: list[str] = Field(description="점수를 깎은 이유와 고칠 점, 한 문장씩")
    action: Literal["REWRITE", "NEXT_CANDIDATE", "MORE_EVIDENCE"] = Field(
        description="REWRITE 설명과 체크리스트 보완, NEXT_CANDIDATE 다른 조합으로 교체, MORE_EVIDENCE 규정 근거 추가 검색"
    )
