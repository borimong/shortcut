"""business-mcp: 촬영 업무·온톨로지·외부 서비스 기능을 도구로 공개한다 (계약 rc2, contracts/mcp-tools.json).

아키텍처 v2의 ontology-mcp, external-mcp 도구를 교안 기준 두 Server 구성에 맞춰 이 서버에 합쳤다.
- 모든 도구는 backend `/internal/**` API 하나에 1:1로 대응한다.
- 검증(HARD 5)과 점수(SOFT 6)는 backend(Spring Boot) 제약·점수 엔진이 한다. 이 서버는 규칙을 갖지 않는다.
- ctx는 Agent가 자동 주입한다. Agent는 모델에게 보이는 스키마에서 ctx를 빼야 한다.

실행:  python -m business_mcp.server        → http://0.0.0.0:9101/mcp
"""
from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .backend import BackendClient, BackendError
from .errors import to_tool_message

# ---------------------------------------------------------------- 공통 타입

Ctx = Annotated[
    dict[str, Any],
    Field(description="Agent가 자동 주입하는 사용자 컨텍스트 {id, role, projectId, taskId}. 모델은 채우지 않는다."),
]
Date = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="날짜 YYYY-MM-DD (Asia/Seoul)")]
Time = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$", description="시각 HH:mm")]
PlanId = Annotated[str, Field(pattern=r"^P\d+$", description="1/2/3안 ID: P1, P2, P3")]
EntityType = Literal["ACTOR", "SCENE", "BLOCK", "LOCATION", "EQUIPMENT", "CONTRACT", "BOOKING", "PLAN_SET", "REGULATION", "PERSON"]

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
READ_EXTERNAL = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
WRITE_REVERSIBLE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
WRITE_DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)


class Choice(BaseModel):
    """요소마다 어느 안에서 가져올지. 예: 장소는 2안, 장비는 1안, 시간대는 2안"""

    location: PlanId
    equipment: PlanId
    time: PlanId


class ExtraConstraint(BaseModel):
    """승인자 거절 사유를 바꾼 추가 제약. 다음 루프부터 HARD로 검사된다."""

    kind: Literal["EXCLUDE_LOCATION", "EXCLUDE_TIME_WINDOW", "EXCLUDE_PACKAGE", "MAX_EXTRA_COST"]
    locationId: str | None = Field(default=None, description="EXCLUDE_LOCATION, 또는 EXCLUDE_TIME_WINDOW를 특정 장소에만 걸 때")
    packageId: str | None = Field(default=None, description="EXCLUDE_PACKAGE")
    start: Time | None = Field(default=None, description="EXCLUDE_TIME_WINDOW 시작")
    end: Time | None = Field(default=None, description="EXCLUDE_TIME_WINDOW 끝")
    amount: int | None = Field(default=None, ge=0, description="MAX_EXTRA_COST 상한(원)")
    reason: str = Field(description="거절 사유 원문 요약. 예: 성수 스튜디오 오후 공사 소음")
    fromRole: str | None = Field(default=None, description="거절한 승인자 역할. 예: SOUND_LEAD")


class Weights(BaseModel):
    """SOFT 6개 기준 가중치. 합이 1이 아니어도 backend가 정규화한다. 감독 지시가 없으면 넘기지 않는다."""

    location: float = Field(ge=0)
    equipment: float = Field(ge=0)
    weather: float = Field(ge=0)
    budget: float = Field(ge=0)
    time: float = Field(ge=0)
    distance: float = Field(ge=0)


def _dump(items):
    return [i.model_dump(exclude_none=True) for i in items] if items else []


# ---------------------------------------------------------------- 서버


def create_server(backend: BackendClient | None = None) -> FastMCP:
    mcp = FastMCP("business")
    be = backend or BackendClient()

    async def call(method: str, path: str, ctx: dict, **kw: Any) -> Any:
        try:
            return await be.request(method, path, ctx, **kw)
        except BackendError as err:
            raise ToolError(to_tool_message(err)) from err
        except ValueError as err:
            raise ToolError(f"[BAD_CONTEXT] {err}") from err

    # ============================================================ 온톨로지 (영향 범위)

    @mcp.tool(annotations=READ_ONLY)
    async def get_entity_context(entity_type: EntityType, entity_id: str, ctx: Ctx) -> dict:
        """엔티티 하나와 직접 연결된 관계를 가져온다 (지식그래프 1단계).
        반환: {entity:{type,id,label,attrs}, relations:[{relation, direction(out|in), target:{type,id,label}, attrs}]}.
        관계 예: ACTOR-HAS_CONTRACT→CONTRACT(현재 버전), ACTOR-APPEARS_IN→SCENE, BLOCK-SHOT_AT→LOCATION, LOCATION-BOOKED_AS→BOOKING.
        배우에게 지금 적용되는 계약서 버전(docId)을 확인할 때 쓴다. 계약 조항 검색은 반드시 이 docId로 한다."""
        return await call("GET", f"/internal/ontology/entities/{entity_type}/{entity_id}", ctx)

    @mcp.tool(annotations=READ_ONLY)
    async def find_impacted_entities(
        event_type: Literal["WEATHER", "ACTOR_SCHEDULE", "LOCATION_CANCELLED", "EQUIPMENT_FAILURE"],
        entity_type: Literal["LOCATION", "ACTOR", "EQUIPMENT"],
        entity_id: str,
        date: Date,
        ctx: Ctx,
        start: Time | None = None,
        end: Time | None = None,
    ) -> dict:
        """변경 이벤트가 걸린 엔티티에서 영향받는 블록·씬·배우·계약·예약·규정을 한 번에 묶어 온다.
        예: WEATHER + LOCATION L01 + 13:00~18:00 → 그 시간 야외 블록과 출연 배우의 현재 계약서 docId.
        반환: {event, blocks:[{blockId, locationId, start, end, hasPlanSet}], scenes, actors:[{actorId, name, currentContractDocId,
        contractVersion, managerUserIds}], locations, equipment, bookings, regulationDocIds}.
        재계획을 시작할 때 가장 먼저 호출한다."""
        return await call("POST", "/internal/ontology/impact", ctx, json={
            "eventType": event_type, "entityType": entity_type, "entityId": entity_id, "date": date, "start": start, "end": end})

    @mcp.tool(annotations=WRITE_REVERSIBLE)
    async def link_entity(from_type: EntityType, from_id: str, relation: str, to_type: EntityType, to_id: str, ctx: Ctx,
                          attrs: dict[str, Any] | None = None) -> dict:
        """지식그래프에 관계를 하나 추가한다. 예: 확정된 계획안의 BLOCK-SHOT_AT→LOCATION, 새 예약 LOCATION-BOOKED_AS→BOOKING.
        relation은 대문자 동사형(SHOT_AT, BOOKED_AS 등). 반환: {linkId, ...}. 확정(commit_plan) 이후에 호출한다."""
        return await call("POST", "/internal/ontology/links", ctx, json={
            "fromType": from_type, "fromId": from_id, "relation": relation, "toType": to_type, "toId": to_id, "attrs": attrs or {}})

    # ============================================================ 계획안 (재평가·재조합·검증)

    @mcp.tool(annotations=READ_ONLY)
    async def get_plan_set(block_id: str, date: Date, ctx: Ctx) -> dict:
        """블록(예: B2)에 제작사가 미리 만든 1/2/3안과 현재 배치를 가져온다.
        반환: {blockId, dataVersion, current, plans:{P1|P2|P3:{label, locationId, locationName, packageId, packageName, start, end, extraCost}}, elements}.
        요소는 장소(location), 장비(equipment), 시간대(time) 세 가지다."""
        return await call("GET", f"/internal/plan-sets/{block_id}", ctx, params={"date": date})

    @mcp.tool(annotations=READ_ONLY)
    async def get_availability(entity_type: Literal["ACTOR", "LOCATION", "EQUIPMENT"], entity_id: str, date: Date, ctx: Ctx) -> dict:
        """배우·장소·장비의 그날 가능 시간과 이미 잡힌 블록을 가져온다.
        반환: {entityType, entityId, date, windows:[{start,end}], busy:[{blockId,start,end}]}. windows 밖은 쓸 수 없다."""
        return await call("GET", "/internal/availability", ctx, params={"entityType": entity_type, "entityId": entity_id, "date": date})

    @mcp.tool(annotations=READ_ONLY)
    async def evaluate_plans(block_id: str, ctx: Ctx, weights: Weights | None = None,
                             extra_constraints: list[ExtraConstraint] | None = None) -> dict:
        """1/2/3안을 현재 조건으로 다시 평가하고, 요소 단위 조합(최대 27개)을 backend 엔진이 전부 검증·채점해 순위를 돌려준다.
        반환: {evaluated, feasibleCount, ranked:[{choice, planHash, total(0~1), scores:{location,equipment,weather,budget,time,distance},
        extraCost(원), totalKm, recombined}], originalPlans:{P1:{feasible,total?}}, infeasibleByCode, weights, dataVersion}.
        weights는 감독이 가중치를 바꾸라고 했을 때만 넘긴다(예: 웃돈 OK → budget↓ location·equipment↑).
        extra_constraints에는 지난 루프 거절 사유를 넣는다. ranked가 비면 세 안 모두 불가이므로 사람에게 보고한다."""
        return await call("POST", "/internal/plans/evaluate", ctx, json={
            "blockId": block_id, "weights": weights.model_dump() if weights else None, "extraConstraints": _dump(extra_constraints)})

    @mcp.tool(annotations=READ_ONLY)
    async def build_schedule(block_id: str, choice: Choice, ctx: Ctx, extra_constraints: list[ExtraConstraint] | None = None) -> dict:
        """선택한 요소 조합으로 블록을 다시 놓고 하루 계획 전체를 만든다(스케줄러). 판정은 하지 않고 데이터도 바꾸지 않는다.
        반환: {planHash, dataVersion, block, day:[블록], extraCost(원), totalKm, changes:[{element, from, to}], bookingNeeded}.
        evaluate_plans 순위에 없는 조합을 직접 확인하고 싶을 때 쓴다. 받은 planHash로 validate_plan을 부른다."""
        return await call("POST", "/internal/plans/build", ctx, json={
            "blockId": block_id, "choice": choice.model_dump(), "extraConstraints": _dump(extra_constraints)})

    @mcp.tool(annotations=READ_ONLY)
    async def validate_plan(plan_hash: str, ctx: Ctx, weights: Weights | None = None) -> dict:
        """후보(planHash) 하나를 HARD 5분류(CONTRACT, SCHEDULE, LAW, BUDGET_LIMIT, NO_FILMING_ZONE)로 검증하고 SOFT 6개로 채점한다.
        반환: {planHash, valid, violations:[{category, code, target, detail, source:{docId,section}|null, hint}], scores, weights, total}.
        승인 요청(save_plan) 직전에 반드시 호출한다. valid=false면 승인으로 넘기지 말고 다른 조합을 고른다."""
        return await call("POST", "/internal/plans/validate", ctx, json={"planHash": plan_hash, "weights": weights.model_dump() if weights else None})

    # ============================================================ 변경 (승인·확정·예약)

    @mcp.tool(annotations=WRITE_REVERSIBLE)
    async def save_plan(plan_hash: str, reason: str, ctx: Ctx, weights: Weights | None = None) -> dict:
        """이번 루프의 최적안 1개를 변경안(예: v8)으로 저장하고 필수 승인자를 지정받는다. 확정 계획은 바뀌지 않는다.
        reason에는 변경 사유와 재조합 내용을 한두 문장으로 적는다(예: 13시 이후 우천으로 1안 불가 → 장소 2안 + 장비 1안 + 시간대 2안).
        반환: {planId, version, status, dataVersion, requiredApprovers:[{role, roleName, userId, scope, status}], bookingNeeded, total}.
        backend가 한 번 더 검증하므로 위반안은 HARD_VIOLATION으로 거부된다. 저장 후에는 승인 대기(interrupt)로 간다."""
        return await call("POST", "/internal/plans", ctx, json={
            "planHash": plan_hash, "reason": reason, "weights": weights.model_dump() if weights else None})

    @mcp.tool(annotations=WRITE_DESTRUCTIVE)
    async def commit_plan(plan_id: int, data_version: int, ctx: Ctx) -> dict:
        """필수 승인자 전원이 승인한 변경안을 확정 계획으로 바꾼다. 되돌리기 어렵다. 확정되면 backend가 콜시트 배포와 알림을 큐에 넣는다.
        data_version은 save_plan이 돌려준 값이다. 그 사이 원본이 바뀌었으면 STALE_PLAN으로 거부된다.
        반환: {planId, scheduleVersion, dataVersion, callsheetJobs}. 승인 전에는 APPROVAL_REQUIRED로 거부된다."""
        return await call("POST", f"/internal/plans/{plan_id}/commit", ctx, json={"dataVersion": data_version},
                          idempotency_key=f"{ctx.get('taskId')}-commit_plan-{plan_id}")

    @mcp.tool(annotations=WRITE_DESTRUCTIVE)
    async def request_location_booking(plan_id: int, location_id: str, ctx: Ctx) -> dict:
        """승인된 변경안의 장소 예약(아워플레이스)을 요청한다. 외부 예약·결제로 이어지므로 되돌리기 어렵다.
        공개 예약 API가 확인되지 않아, 지금은 제작실장이 직접 예약한 뒤 완료 처리하는 MANUAL_PENDING 상태로 만든다.
        반환: {bookingId, status, assigneeRole, note}. save_plan 결과의 bookingNeeded가 true일 때만, 승인 후에 호출한다."""
        return await call("POST", "/internal/bookings", ctx, json={"planId": plan_id, "locationId": location_id},
                          idempotency_key=f"{ctx.get('taskId')}-request_location_booking-{plan_id}")

    # ============================================================ 외부 서비스

    @mcp.tool(annotations=READ_EXTERNAL)
    async def get_weather(location_id: str, date: Date, ctx: Ctx) -> dict:
        """장소의 시간대별 강수 확률(기상청 단기예보)을 가져온다.
        반환: {locationId, date, outdoor, hourly:[{hour:"13:00", rainProb(%)}], rainThreshold}.
        실내 장소는 hourly가 비어 있다. 우천 판정 자체는 validate_plan이 한다."""
        return await call("GET", "/internal/external/weather", ctx, params={"locationId": location_id, "date": date})

    @mcp.tool(annotations=READ_EXTERNAL)
    async def search_locations(ctx: Ctx, keyword: str | None = None, area: str | None = None,
                               indoor: bool | None = None, min_area_pyeong: int | None = None) -> dict:
        """아워플레이스에서 대체 장소 후보를 찾는다. keyword 예: 자연광, area 예: 성수.
        반환: {source, results:[{placeId, name, area, indoor, areaPyeong, pricePerHour(원), naturalLight}]}.
        1/2/3안이 모두 불가할 때 사람에게 보고할 대안 목록을 만들 때 쓴다(4안 추천은 확장 기능)."""
        params = {"keyword": keyword, "area": area, "minArea": min_area_pyeong,
                  "indoor": None if indoor is None else str(indoor).lower()}
        return await call("GET", "/internal/external/locations", ctx, params=params)

    @mcp.tool(annotations=READ_EXTERNAL)
    async def get_route(from_location_id: str, to_location_id: str, ctx: Ctx) -> dict:
        """두 장소 사이 이동 거리와 시간을 가져온다. 반환: {from, to, km, minutes}."""
        return await call("GET", "/internal/external/route", ctx, params={"from": from_location_id, "to": to_location_id})

    @mcp.tool(annotations=READ_EXTERNAL)
    async def get_equipment_quote(package_id: str, date: Date, ctx: Ctx) -> dict:
        """장비 묶음(PKG-BASE, PKG-LIGHT, PKG-MIN)의 구성, 대여 가능 시간, 추가 비용 견적을 가져온다.
        반환: {packageId, name, items:[{equipmentId, name, available}], extraCost(원)}."""
        return await call("GET", "/internal/external/equipment-quote", ctx, params={"packageId": package_id, "date": date})

    return mcp


mcp = create_server()

if __name__ == "__main__":
    mcp.run(transport="http", host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "9101")), path="/mcp")
