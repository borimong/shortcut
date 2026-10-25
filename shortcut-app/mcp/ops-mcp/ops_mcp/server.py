"""ops-mcp: 확정 뒤 실행 Agent가 쓰는 가상 외부 서비스 도구를 MCP로 공개한다.

- 실행팀(장소, 장비, 허가, 이동, 연락, 장부 Agent) 전용이다. 계획 단계 도구는 business-mcp에 있다.
- 모든 도구는 backend `/internal/ops/**` API 하나에 1:1로 대응한다. 가용 판단, 금액 계산, 허가 판정은
  backend OpsService가 결정론적으로 하고, 이 서버는 DB에 접근하지 않으며 규칙도 갖지 않는다.
- 조회 도구 8개, 쓰기 도구 10개. 쓰기 도구는 같은 요청을 다시 보내도 기존 결과를 돌려준다(backend 멱등).

실행:  python -m ops_mcp.server        → http://0.0.0.0:9103/mcp (Streamable HTTP)
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

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
# 가상 외부 서비스에 예약, 신청, 발송을 남기지만 backend가 멱등으로 처리하므로 같은 요청을 다시 보내도 결과가 같다.
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

# ---------------------------------------------------------------- 공통 타입

ShootDayId = Annotated[int, Field(ge=1, description="작업 지시서의 촬영일 ID (시연 데이터는 1)")]
TaskId = Annotated[int, Field(ge=1, description="작업 지시서의 작업 ID. 예약과 발송 기록을 이 작업에 묶는다")]
LocationId = Annotated[int, Field(ge=1, description="작업 지시서에 적힌 확정 장소 ID")]
HourMinute = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$", description="HH:mm")]
EquipmentIds = Annotated[list[int], Field(min_length=1, description="작업 지시서에 적힌 장비 ID 목록")]
ReservationId = Annotated[str, Field(min_length=1, description="예약 번호. 예: R-3001")]
BookingId = Annotated[str, Field(min_length=1, description="예약 번호. 렌탈은 RB-, 차량은 TB-로 시작한다")]


class Message(BaseModel):
    """한 사람에게 보낼 안내문 하나."""

    recipient_id: str = Field(
        pattern=r"^(ACTOR|USER|VENDOR):[A-Za-z0-9_\-]+$",
        description="contacts_for_change 결과의 recipientId. 예: ACTOR:1, USER:ad1, VENDOR:venue",
    )
    text: str = Field(min_length=1, max_length=1000, description="그 사람에게 맞춘 안내문")

    def to_backend(self) -> dict[str, Any]:
        return {"recipientId": self.recipient_id, "text": self.text}


class LedgerEntry(BaseModel):
    """장부에 남길 항목 하나. 금액은 넣지 않는다. backend가 ref_type, ref_id가 가리키는 예약 행에서 직접 읽는다."""

    account: Literal["VENUE", "EQUIPMENT_RENTAL", "TRANSPORT", "PERMIT_FEE", "CANCEL_FEE"] = Field(
        description="계정. 장소비 VENUE, 장비 임차료 EQUIPMENT_RENTAL, 차량비 TRANSPORT, 인허가 수수료 PERMIT_FEE, 취소 수수료 CANCEL_FEE"
    )
    memo: str = Field(min_length=1, max_length=200, description="적요. 무엇 때문에 쓴 돈인지 한 문장")
    ref_type: Literal["RESERVATION", "RENTAL", "TRANSPORT", "PERMIT"] = Field(description="근거가 되는 예약 종류")
    ref_id: str = Field(min_length=1, description="예약 번호(R-, RB-, TB-, PM-로 시작)")

    def to_backend(self) -> dict[str, Any]:
        return {"account": self.account, "memo": self.memo, "refType": self.ref_type, "refId": self.ref_id}


# ---------------------------------------------------------------- 서버


def build_server(backend: BackendClient | None = None) -> FastMCP:
    """backend 클라이언트를 주입받아 도구를 등록한 서버를 만든다. 테스트는 MockTransport를 넘긴다."""
    backend = backend or BackendClient()
    mcp = FastMCP(
        "ops-mcp",
        instructions=(
            "확정된 콜시트를 실제로 실행하는 가상 외부 서비스(장소 예약, 장비 렌탈, 촬영 허가, 차량, 연락, 제작비 장부)입니다. "
            "확정안 범위(장소, 시간, 장비) 밖으로 바꾸지 말고, 실패하면 다른 대안을 찾지 말고 결과를 그대로 보고하세요. "
            "금액, 가용 여부, 허가 판정은 도구 결과를 그대로 쓰세요."
        ),
    )

    async def call(method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        try:
            return await backend.request(method, path, params=params, json=json)
        except BackendError as err:
            raise ToolError(to_tool_message(err)) from err

    # ---------------- 장소 (가상 아워플레이스)

    @mcp.tool(annotations=READ_ONLY)
    async def venue_check(shoot_day_id: ShootDayId, location_id: LocationId, start: HourMinute, end: HourMinute) -> dict:
        """확정 장소가 확정 시간대에 비어 있는지와 장소비를 확인한다. 장소 예약의 첫 단계다.
        결과의 reservations에는 그 촬영일의 모든 예약이 있으므로, 이전 장소의 예약이 남아 있으면 venue_cancel로 취소한다.
        available이 true면 venue_hold로 가예약하고, false면 예약하지 말고 reason을 실패로 보고한다."""
        params = {"shootDayId": shoot_day_id, "start": start, "end": end}
        return await call("GET", f"/internal/ops/venues/{location_id}/availability", params=params)

    @mcp.tool(annotations=WRITE)
    async def venue_hold(
        shoot_day_id: ShootDayId, task_id: TaskId, location_id: LocationId, start: HourMinute, end: HourMinute
    ) -> dict:
        """확정 장소를 확정 시간대로 가예약(HELD)한다. venue_check로 가용을 확인한 뒤에 부른다.
        확정 때 남은 처리 대기 예약이 있으면 그 예약을 이어받는다. 결과의 reservationId로 venue_confirm을 불러 확정한다.
        VENUE_CONFLICT가 나면 다른 시간이나 장소를 시도하지 말고 실패로 보고한다."""
        body = {"shootDayId": shoot_day_id, "taskId": task_id, "locationId": location_id, "start": start, "end": end}
        return await call("POST", "/internal/ops/venues/holds", json=body)

    @mcp.tool(annotations=WRITE)
    async def venue_confirm(reservation_id: ReservationId) -> dict:
        """가예약을 확정(CONFIRMED)한다. 장소 예약의 마지막 단계이고, 확정된 예약 번호가 허가, 차량, 연락 Agent의 입력이 된다."""
        return await call("POST", f"/internal/ops/venues/reservations/{reservation_id}/confirm")

    @mcp.tool(annotations=WRITE)
    async def venue_cancel(
        reservation_id: ReservationId,
        reason: Annotated[str, Field(min_length=1, max_length=200, description="취소 사유. 예: 장소 변경으로 이전 예약 취소")],
    ) -> dict:
        """예약을 취소한다. 장소가 바뀌어 이전 장소 예약이 필요 없을 때나, 수정 요청으로 다시 예약할 때 쓴다.
        확정 예약을 취소하면 장소비의 10% 취소 수수료(cancelFeeKrw)가 생기며, 장부 Agent가 이 금액을 기록한다."""
        return await call("POST", f"/internal/ops/venues/reservations/{reservation_id}/cancel", json={"reason": reason})

    # ---------------- 장비 (가상 렌탈사)

    @mcp.tool(annotations=READ_ONLY)
    async def rental_quote(shoot_day_id: ShootDayId, equipment_ids: EquipmentIds, start: HourMinute, end: HourMinute) -> dict:
        """확정 장비 묶음의 렌탈 견적과 도착 시각을 받는다. 장비 렌탈의 첫 단계다.
        owned가 true인 장비는 보유 장비라 비용이 0이다. 결과의 bookings에 이전 렌탈 예약이 남아 있으면
        확정안에 없는 장비 예약은 rental_cancel로 취소하고, 확정 장비는 rental_book으로 예약한다."""
        body = {"shootDayId": shoot_day_id, "equipmentIds": equipment_ids, "start": start, "end": end}
        return await call("POST", "/internal/ops/rentals/quote", json=body)

    @mcp.tool(annotations=WRITE)
    async def rental_book(
        shoot_day_id: ShootDayId, task_id: TaskId, equipment_ids: EquipmentIds, start: HourMinute, end: HourMinute
    ) -> dict:
        """확정 장비 묶음을 렌탈 예약(BOOKED)한다. rental_quote로 견적을 본 뒤에 부른다.
        결과의 bookingId와 deliveryAt(장비 도착 시각)은 연락 Agent가 안내문에 쓴다."""
        body = {
            "shootDayId": shoot_day_id,
            "taskId": task_id,
            "equipmentIds": equipment_ids,
            "start": start,
            "end": end,
        }
        return await call("POST", "/internal/ops/rentals/bookings", json=body)

    @mcp.tool(annotations=WRITE)
    async def rental_cancel(booking_id: BookingId) -> dict:
        """렌탈 예약을 취소한다. 장비가 바뀌어 이전 예약이 필요 없을 때 쓴다. 총액의 10%가 취소 수수료로 생긴다."""
        return await call("POST", f"/internal/ops/rentals/bookings/{booking_id}/cancel")

    # ---------------- 촬영 허가 (가상 허가 기관)

    @mcp.tool(annotations=READ_ONLY)
    async def permit_check_requirement(
        shoot_day_id: ShootDayId,
        location_id: LocationId,
        start: HourMinute,
        end: HourMinute,
        drone: Annotated[bool, Field(description="확정 장비에 드론이 있으면 true")],
    ) -> dict:
        """확정 장소, 시간대에 촬영 허가가 필요한지 확인한다. 촬영 허가의 첫 단계다.
        kinds에 있는 종류(야외 장소 LOCATION, 드론 DRONE)마다 permit_apply로 신청한다. required가 false면 신청하지 않는다.
        withinWindow가 false거나 noFlyZone이 true면 반려될 수 있으니 결과를 그대로 보고한다."""
        params = {"shootDayId": shoot_day_id, "locationId": location_id, "start": start, "end": end, "drone": drone}
        return await call("GET", "/internal/ops/permits/requirement", params=params)

    @mcp.tool(annotations=WRITE)
    async def permit_apply(
        shoot_day_id: ShootDayId,
        task_id: TaskId,
        location_id: LocationId,
        start: HourMinute,
        end: HourMinute,
        kind: Annotated[Literal["LOCATION", "DRONE"], Field(description="허가 종류. 야외 장소 LOCATION, 드론 촬영 DRONE")],
    ) -> dict:
        """관할 기관에 촬영 허가를 신청하고 심사 결과(APPROVED 또는 DENIED)를 바로 받는다.
        승인되면 conditions(촬영 가능 시간 등 조건)를 연락 Agent가 안내문에 쓴다. DENIED면 denialReason을 실패로 보고한다."""
        body = {
            "shootDayId": shoot_day_id,
            "taskId": task_id,
            "locationId": location_id,
            "start": start,
            "end": end,
            "kind": kind,
        }
        return await call("POST", "/internal/ops/permits", json=body)

    @mcp.tool(annotations=READ_ONLY)
    async def permit_status(permit_id: Annotated[str, Field(min_length=1, description="허가 번호. 예: PM-1001")]) -> dict:
        """신청한 허가의 현재 상태와 조건을 다시 조회한다."""
        return await call("GET", f"/internal/ops/permits/{permit_id}")

    # ---------------- 이동 수단 (가상 차량 업체)

    @mcp.tool(annotations=READ_ONLY)
    async def transport_quote(
        shoot_day_id: ShootDayId,
        dest_location_id: Annotated[int, Field(ge=1, description="이동할 확정 장소 ID")],
        start: HourMinute,
        headcount: Annotated[int, Field(ge=1, le=200, description="이동 인원")],
        equipment_ids: EquipmentIds,
    ) -> dict:
        """오전 촬영지에서 확정 장소까지 차량 견적, 출발 시각(departAt), 집결 장소(pickup)를 받는다. 이동 수단의 첫 단계다.
        recommended를 기본으로 transport_book을 부른다. bookings에 다른 장소로 가는 이전 차량 예약이 있으면 transport_cancel로 취소한다."""
        body = {
            "shootDayId": shoot_day_id,
            "destLocationId": dest_location_id,
            "start": start,
            "headcount": headcount,
            "equipmentIds": equipment_ids,
        }
        return await call("POST", "/internal/ops/transport/quote", json=body)

    @mcp.tool(annotations=WRITE)
    async def transport_book(
        shoot_day_id: ShootDayId,
        task_id: TaskId,
        dest_location_id: Annotated[int, Field(ge=1, description="이동할 확정 장소 ID")],
        vehicle: Annotated[
            Literal["VAN_12", "BUS_25", "TRUCK_1T"],
            Field(description="차량 종류. 12인승 밴 VAN_12, 25인승 버스 BUS_25, 장비 트럭 TRUCK_1T"),
        ],
        count: Annotated[int, Field(ge=1, le=10, description="대수")],
        depart_at: HourMinute,
        pickup: Annotated[str, Field(min_length=1, max_length=60, description="transport_quote 결과의 집결 장소")],
        headcount: Annotated[int, Field(ge=1, le=200, description="이동 인원")],
    ) -> dict:
        """차량을 예약(BOOKED)한다. transport_quote 결과의 차량, 대수, 출발 시각, 집결 장소를 그대로 쓴다.
        결과의 bookingId, departAt, pickup은 연락 Agent가 안내문에 쓴다."""
        body = {
            "shootDayId": shoot_day_id,
            "taskId": task_id,
            "destLocationId": dest_location_id,
            "vehicle": vehicle,
            "count": count,
            "departAt": depart_at,
            "pickup": pickup,
            "headcount": headcount,
        }
        return await call("POST", "/internal/ops/transport/bookings", json=body)

    @mcp.tool(annotations=WRITE)
    async def transport_cancel(booking_id: BookingId) -> dict:
        """차량 예약을 취소한다. 장소가 바뀌어 이전 목적지 차량이 필요 없을 때 쓴다. 비용의 10%가 취소 수수료로 생긴다."""
        return await call("POST", f"/internal/ops/transport/bookings/{booking_id}/cancel")

    # ---------------- 연락 (가상 메시지 발송)

    @mcp.tool(annotations=READ_ONLY)
    async def contacts_for_change(
        shoot_day_id: ShootDayId,
        changed: Annotated[
            list[Literal["LOCATION", "TIME", "EQUIPMENT"]],
            Field(min_length=1, description="이번 확정에서 바뀐 요소"),
        ],
    ) -> dict:
        """바뀐 요소에 영향받는 연락 대상(배우, 스태프, 예약 업체)과 채널, 연락 이유를 돌려준다. 연락의 첫 단계다.
        사람마다 맞춘 안내문을 써서 send_message 한 번에 모두 보낸다."""
        params = {"shootDayId": shoot_day_id, "changed": ",".join(changed)}
        return await call("GET", "/internal/ops/contacts", params=params)

    @mcp.tool(annotations=WRITE)
    async def send_message(
        shoot_day_id: ShootDayId,
        task_id: TaskId,
        messages: Annotated[list[Message], Field(min_length=1, max_length=40, description="받는 사람별 안내문")],
    ) -> dict:
        """여러 사람에게 안내문을 한 번에 보낸다. 안내문에는 바뀐 내용, 확정된 예약 번호, 집결 시각(HH:mm)과 장소,
        장비 도착 시각, 허가 조건처럼 그 사람이 움직이는 데 필요한 것을 담는다. 보낸 뒤 get_replies로 응답을 모은다."""
        body = {"shootDayId": shoot_day_id, "taskId": task_id, "messages": [m.to_backend() for m in messages]}
        return await call("POST", "/internal/ops/messages", json=body)

    @mcp.tool(annotations=READ_ONLY)
    async def get_replies(task_id: TaskId) -> dict:
        """이 작업으로 보낸 안내문의 응답(확인 수, 질문, 미응답 수)을 모은다. 질문이 오면 그 내용을 보고에 담는다."""
        return await call("GET", "/internal/ops/messages/replies", params={"taskId": task_id})

    # ---------------- 제작비 장부

    @mcp.tool(annotations=WRITE)
    async def ledger_record(
        shoot_day_id: ShootDayId,
        task_id: TaskId,
        entries: Annotated[list[LedgerEntry], Field(min_length=1, max_length=30, description="기록할 항목")],
    ) -> dict:
        """실행 단계에서 생긴 비용(장소비, 장비 임차료, 차량비, 허가 수수료, 취소 수수료)을 장부에 기록한다.
        금액은 넣지 않는다. backend가 ref_id가 가리키는 예약 행에서 직접 읽어 기록하고, 블록 예산 대비 집행 결과(budget)를 돌려준다.
        Agent는 계정 분류와 적요(왜 쓴 돈인지)만 쓴다."""
        body = {"shootDayId": shoot_day_id, "taskId": task_id, "entries": [e.to_backend() for e in entries]}
        return await call("POST", "/internal/ops/ledger", json=body)

    @mcp.tool(annotations=READ_ONLY)
    async def ledger_budget_status(shoot_day_id: ShootDayId) -> dict:
        """촬영일의 블록 예산 상한, 집행 합계, 잔액, 초과 여부와 장부 항목을 조회한다. 기록 뒤 예산 상태를 보고할 때 쓴다."""
        return await call("GET", "/internal/ops/ledger/budget", params={"shootDayId": shoot_day_id})

    return mcp


def main() -> None:
    """compose 안에서 Streamable HTTP로 실행한다."""
    server = build_server(BackendClient())
    server.run(
        transport="http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "9103")),
        path="/mcp",
    )


if __name__ == "__main__":
    main()
