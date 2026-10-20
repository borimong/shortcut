"""business-mcp: 촬영 업무 기능을 도구로 공개한다 (아키텍처 문서 7장).

- 모든 도구는 backend `/internal/**` API 하나에 1:1로 대응한다.
- 업무 규칙(근로시간, 허가 시간대 등)은 여기서 판단하지 않는다. 판정은 validate_schedule로 backend에 맡긴다.
- 모델은 함수 본문을 보지 않고 docstring만 읽는다. docstring에 받는 값, 돌려주는 값(단위), 언제 쓰는지를 적는다.
- ctx는 Agent가 자동으로 주입한다. Agent는 모델에게 보이는 도구 스키마에서 ctx를 빼야 한다 (계약 3).

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
    Field(description="Agent가 자동 주입하는 사용자 컨텍스트 {id, role, productionId, taskId}. 모델은 채우지 않는다."),
]
Date = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="날짜 YYYY-MM-DD (Asia/Seoul)")]

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE_REVERSIBLE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
WRITE_DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)


class Slot(BaseModel):
    """초안의 촬영 칸 하나 (문서 7장 draft 형식)."""

    date: Date
    sceneId: str = Field(description="씬 ID, 예: S21")
    locationId: str = Field(description="장소 ID, 예: L02")
    start: str = Field(pattern=r"^\d{2}:\d{2}$", description="시작 시각 HH:mm")
    end: str = Field(pattern=r"^\d{2}:\d{2}$", description="종료 시각 HH:mm")
    equipmentIds: list[str] = Field(default_factory=list, description="사용 장비 ID 목록")


class ScheduleDraft(BaseModel):
    """재계획 초안. 영향받는 날짜 범위만 담고, 범위 밖은 기준 스케줄을 그대로 쓴다."""

    baseScheduleId: int = Field(description="기준이 되는 현재 확정 스케줄 ID")
    dateFrom: Date
    dateTo: Date
    slots: list[Slot]


# ---------------------------------------------------------------- 서버 생성


def create_server(backend: BackendClient | None = None) -> FastMCP:
    """테스트에서 가짜 backend를 넣을 수 있도록 서버를 함수로 만든다."""
    mcp = FastMCP("business")
    be = backend or BackendClient()

    async def call(method: str, path: str, ctx: dict, **kw: Any) -> Any:
        try:
            return await be.request(method, path, ctx, **kw)
        except BackendError as err:
            raise ToolError(to_tool_message(err)) from err
        except ValueError as err:  # ctx 누락 등 호출 형식 문제
            raise ToolError(f"[BAD_CONTEXT] {err}") from err

    def idem(ctx: dict, tool: str) -> str:
        return f"{ctx.get('taskId')}-{tool}"

    # ------------------------------------------------------------ 조회 도구

    @mcp.tool(annotations=READ_ONLY)
    async def get_shooting_schedule(date_from: Date, date_to: Date, ctx: Ctx) -> list[dict]:
        """현재 확정된 촬영 스케줄을 날짜 범위로 조회한다.
        반환: [{date, slots:[{sceneId, locationId, start, end, equipmentIds}]}] (시각은 HH:mm).
        재계획을 시작할 때 영향받는 날짜의 기존 배치를 확인하려고 가장 먼저 호출한다."""
        return await call("GET", "/internal/schedules", ctx, params={"from": date_from, "to": date_to})

    @mcp.tool(annotations=READ_ONLY)
    async def get_scene(scene_id: str, ctx: Ctx) -> dict:
        """씬 ID(예: S21)로 씬 정보를 조회한다.
        반환: {sceneId, title, locationId, indoor(실내 여부), actorIds, equipmentIds, durationMin(촬영 소요 분)}.
        영향받는 씬의 출연 배우, 장소, 장비를 확인할 때 쓴다."""
        return await call("GET", f"/internal/scenes/{scene_id}", ctx)

    @mcp.tool(annotations=READ_ONLY)
    async def get_scenes_by_location(location_id: str, ctx: Ctx) -> list[dict]:
        """장소 ID(예: L02)에서 촬영하는 모든 씬을 조회한다. 반환 형식은 get_scene의 목록이다.
        날씨나 허가 문제로 특정 장소를 못 쓰게 됐을 때 영향받는 씬을 찾는 데 쓴다."""
        return await call("GET", "/internal/scenes", ctx, params={"locationId": location_id})

    @mcp.tool(annotations=READ_ONLY)
    async def get_actor_availability(actor_id: str, date_from: Date, date_to: Date, ctx: Ctx) -> list[dict]:
        """배우(예: A03)가 촬영 가능한 시간대를 날짜별로 조회한다.
        반환: [{date, available:[{start, end}]}]. 목록에 없는 시간은 촬영할 수 없다.
        배우 스케줄 변경 요청이 오거나, 씬을 다른 날로 옮기기 전에 확인한다."""
        return await call(
            "GET", f"/internal/actors/{actor_id}/availability", ctx, params={"from": date_from, "to": date_to}
        )

    @mcp.tool(annotations=READ_ONLY)
    async def get_location_permit(location_id: str, date: Date, ctx: Ctx) -> dict:
        """장소의 해당 날짜 촬영 허가 상태를 조회한다.
        반환: {permitId, status(REQUESTED|APPROVED|CANCELLED), allowedStart, allowedEnd}.
        야외 장소로 씬을 옮기기 전에 허가 시간대를 확인한다."""
        return await call("GET", f"/internal/locations/{location_id}/permits", ctx, params={"date": date})

    @mcp.tool(annotations=READ_ONLY)
    async def get_weather_forecast(location_id: str, date: Date, ctx: Ctx) -> dict:
        """장소의 날짜별 날씨 예보를 조회한다.
        반환: {date, rainProb(강수 확률 %, 0~100), condition}.
        야외 씬을 그 날 찍어도 되는지 판단할 근거로 쓴다. 판정 자체는 validate_schedule이 한다."""
        return await call("GET", "/internal/weather", ctx, params={"locationId": location_id, "date": date})

    @mcp.tool(annotations=READ_ONLY)
    async def validate_schedule(draft: ScheduleDraft, ctx: Ctx) -> dict:
        """재계획 초안이 제약을 지키는지 backend 제약 엔진으로 검증한다. 데이터는 바꾸지 않는다.
        반환: {valid, violations:[{type, severity(hard|soft), target, detail, source:{docId, section}, hint}],
        softScore(0~1, 높을수록 좋음), changedScenes(기준 대비 바뀐 씬 수)}.
        초안을 만들거나 고칠 때마다 반드시 호출한다. hard 위반이 하나라도 있으면 승인을 요청하지 말고
        hint를 참고해 초안을 고친 뒤 다시 검증한다."""
        return await call("POST", "/internal/schedule/validate", ctx, json=draft.model_dump())

    # ------------------------------------------------------------ 변경 도구

    @mcp.tool(annotations=WRITE_REVERSIBLE)
    async def save_schedule_draft(draft: ScheduleDraft, reason: str, ctx: Ctx) -> dict:
        """검증을 통과했거나 escalate할 초안을 저장하고 draftId를 받는다. 확정 스케줄은 바뀌지 않는다.
        reason에는 재계획 사유를 한 문장으로 적는다. 반환: {draftId}.
        감독 승인을 요청하기 직전에 호출한다."""
        return await call(
            "POST", "/internal/schedule-drafts", ctx, json={"draft": draft.model_dump(), "reason": reason}
        )

    @mcp.tool(annotations=WRITE_DESTRUCTIVE)
    async def confirm_schedule(draft_id: int, ctx: Ctx) -> dict:
        """저장된 초안을 확정 스케줄로 바꾼다. 기존 확정본은 대체된다. 반환: {scheduleId}.
        감독 승인이 기록된 뒤에만 호출한다. 승인 전에는 실행되지 않고 APPROVAL_REQUIRED 오류가 난다."""
        return await call(
            "POST", f"/internal/schedule-drafts/{draft_id}/confirm", ctx, idempotency_key=idem(ctx, "confirm_schedule")
        )

    @mcp.tool(annotations=WRITE_DESTRUCTIVE)
    async def update_permit_status(
        permit_id: int, status: Literal["REQUESTED", "APPROVED", "CANCELLED"], ctx: Ctx
    ) -> dict:
        """촬영 허가 상태를 바꾼다(예: 쓰지 않게 된 장소 허가를 CANCELLED로). 반환: {permitId, status}.
        감독 승인 후, confirm_schedule 다음에 호출한다."""
        return await call(
            "PATCH",
            f"/internal/permits/{permit_id}",
            ctx,
            json={"status": status},
            idempotency_key=f"{idem(ctx, 'update_permit_status')}-{permit_id}",
        )

    @mcp.tool(annotations=WRITE_DESTRUCTIVE)
    async def send_callsheets(schedule_id: int, recipient_ids: list[int], ctx: Ctx) -> dict:
        """확정된 스케줄의 콜시트를 수신자(사용자 ID)에게 발송한다. 되돌릴 수 없다.
        반환: {queued(발송 대기열에 넣은 건수), recipients}.
        반드시 감독 승인 후, confirm_schedule이 성공한 다음에만 호출한다."""
        return await call(
            "POST",
            "/internal/callsheets/send",
            ctx,
            json={"scheduleId": schedule_id, "recipientIds": recipient_ids},
            idempotency_key=idem(ctx, "send_callsheets"),
        )

    return mcp


mcp = create_server()

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "9101")),
        path="/mcp",
    )
