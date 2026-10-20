"""촬영 업무 기능을 Agent가 호출하는 MCP 도구로 노출하는 서버입니다.

업무 규칙은 Spring Boot 한 곳에만 두기 위해 이 서버는 DB에 접근하지 않고
backend 내부 API(/internal/**)를 호출한 결과를 그대로 돌려줍니다.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import BaseModel, Field

BACKEND_URL = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8080")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "local-internal-token")
# 내부 API 한 번이 길어지면 Agent 작업 한도(120초)를 혼자 다 쓰게 되므로 10초에서 끊는다.
REQUEST_TIMEOUT_SECONDS = 10.0

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}

NodeId = Annotated[
    str,
    Field(
        pattern=r"^[A-Z_]+:[A-Za-z0-9_\-]+$",
        description="온톨로지 노드 ID. 형식 TYPE:키 (예: SCENE:S12, ACTOR:1, LOCATION:2)",
    ),
]
ShootDayId = Annotated[int, Field(ge=1, description="촬영일 ID (시연 데이터는 1)")]
HourMinute = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$", description="HH:mm")]


class ExtraConstraint(BaseModel):
    """거절 사유나 지시에서 만든 추가 제약입니다."""

    type: Literal[
        "EXCLUDE_LOCATION",
        "EXCLUDE_LOCATION_TIME",
        "EXCLUDE_EQUIPMENT",
        "MAX_EXTRA_COST",
        "REQUIRE_INDOOR",
        "LATEST_END",
        "EXCLUDE_TIME",
    ]
    location_id: int | None = None
    equipment_id: int | None = None
    from_time: HourMinute | None = None
    to_time: HourMinute | None = None
    time: HourMinute | None = None
    amount: int | None = None
    reason: str = ""
    source: str = ""

    def to_backend(self) -> dict[str, Any]:
        """backend 계약의 camelCase 필드로 바꿉니다."""
        body = {
            "type": self.type,
            "locationId": self.location_id,
            "equipmentId": self.equipment_id,
            "from": self.from_time,
            "to": self.to_time,
            "time": self.time,
            "amount": self.amount,
            "reason": self.reason,
            "source": self.source,
        }
        return {key: value for key, value in body.items() if value is not None}


class Candidate(BaseModel):
    """오후 블록 후보안 하나입니다."""

    location_id: int = Field(ge=1)
    equipment_ids: list[int] = Field(min_length=1)
    start: HourMinute
    end: HourMinute
    source: dict[str, int] | None = Field(
        default=None, description="요소별 출처 안 번호, 예: {location: 2, equipment: 1, time: 2}"
    )

    def to_backend(self) -> dict[str, Any]:
        """backend 계약의 camelCase 필드로 바꿉니다."""
        body: dict[str, Any] = {
            "locationId": self.location_id,
            "equipmentIds": sorted(self.equipment_ids),
            "start": self.start,
            "end": self.end,
        }
        if self.source:
            body["source"] = self.source
        return body


class ChecklistItem(BaseModel):
    """하드 제약별 준수 확인 결과입니다."""

    constraint: str
    status: Literal["PASS", "WARN"]
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """승인 화면 근거 패널에 보여 줄 조항입니다."""

    id: str
    doc_id: str
    title: str
    text: str
    doc_type: str = ""


class BackendClient:
    """backend 내부 API 호출과 오류 변환을 담당합니다."""

    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"X-Internal-Token": token},
            transport=transport,
        )

    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        """내부 API를 호출하고 실패를 모델이 다시 시도할 수 있는 ToolError로 바꿉니다."""
        headers = {}
        acting_user = _acting_user()
        if acting_user:
            headers["X-Acting-User"] = acting_user
        try:
            response = self._client.request(method, path, params=params, json=json, headers=headers)
        except httpx.TimeoutException as error:
            raise ToolError(_error_text("BACKEND_TIMEOUT", "업무 API 응답이 늦습니다.", True)) from error
        except httpx.TransportError as error:
            raise ToolError(_error_text("BACKEND_UNAVAILABLE", "업무 API에 연결할 수 없습니다.", True)) from error
        if response.status_code >= 400:
            raise ToolError(_http_error_text(response))
        if response.status_code == 204 or not response.content:
            return {"ok": True}
        return response.json()


def _acting_user() -> str | None:
    """MCP 요청 헤더에 실린 작업 요청자를 내부 API 감사 기록으로 넘깁니다."""
    try:
        return get_http_headers().get("x-acting-user")
    except RuntimeError:
        return None


def _error_text(code: str, message: str, retryable: bool) -> str:
    # Agent Harness가 정규식으로 code와 retryable을 읽으므로 형식을 고정한다.
    return f"[{code}] {message} (retryable={'true' if retryable else 'false'})"


def _http_error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {}
    code = body.get("code") or f"HTTP_{response.status_code}"
    message = body.get("message") or response.reason_phrase
    # 429와 5xx는 같은 요청을 다시 보내면 성공할 수 있지만 4xx는 인자를 고쳐야 하므로 재시도 대상에서 뺀다.
    retryable = response.status_code == 429 or response.status_code >= 500
    detail = ""
    if body.get("violations"):
        codes = ", ".join(v.get("code", "") for v in body["violations"])
        detail = f" 위반: {codes}."
    if code == "NODE_NOT_FOUND":
        detail = " 노드 ID는 TYPE:키 형식입니다. 예: SCENE:S12, ACTOR:1, LOCATION:2, CONTRACT:contract-actor-a-v3."
    return _error_text(code, f"{message}.{detail}", retryable)


def build_server(backend: BackendClient) -> FastMCP:
    """backend 클라이언트를 주입받아 도구를 등록한 MCP 서버를 만듭니다."""
    mcp = FastMCP(
        "business-mcp",
        instructions=(
            "촬영 업무 데이터(온톨로지, 1/2/3안, 가용 자원, 날씨, 재난 문자, 계획 평가, 변경안 제출과 확정)를 다룹니다. "
            "조회 도구는 자유롭게 써도 되지만 submit_proposal과 commit_plan은 업무 데이터를 바꿉니다."
        ),
    )

    @mcp.tool(annotations=READ_ONLY)
    def get_entity_context(node_id: NodeId) -> dict:
        """온톨로지 노드 하나와 바로 연결된 이웃 노드(관계 이름, 방향 포함)를 돌려준다.
        배우, 씬, 장소, 계약서, 예약 사이의 관계를 확인할 때 쓴다."""
        return backend.request("GET", f"/internal/ontology/nodes/{node_id}")

    @mcp.tool(annotations=READ_ONLY)
    def find_impacted_entities(
        node_id: NodeId,
        depth: Annotated[int, Field(ge=1, le=3, description="탐색 깊이, 기본 2")] = 2,
    ) -> dict:
        """변경이 생긴 노드에서 depth 단계 안에 연결된 노드와 엣지를 모두 돌려준다.
        변경 영향 범위(관련 씬, 배우, 계약서, 예약, 장비)를 한 번에 묶어 볼 때 쓴다."""
        return backend.request("GET", "/internal/ontology/impact", params={"nodeId": node_id, "depth": depth})

    @mcp.tool(annotations=WRITE)
    def link_entity(
        src: NodeId,
        relation: Annotated[str, Field(min_length=1, max_length=20, description="관계 이름, 예: 촬영지, 사용, 출연")],
        dst: NodeId,
    ) -> dict:
        """두 온톨로지 노드 사이에 관계 엣지를 하나 추가한다. 업무 데이터를 바꾸는 도구다."""
        return backend.request("POST", "/internal/ontology/edges", json={"src": src, "relation": relation, "dst": dst})

    @mcp.tool(annotations=READ_ONLY)
    def get_plan_set(shoot_day_id: ShootDayId) -> dict:
        """오후 변경 대상 블록의 씬과 배우, 현재 확정안, 제작사가 미리 만든 1/2/3안(장소, 장비, 시간대)을 돌려준다."""
        return backend.request("GET", f"/internal/shoot-days/{shoot_day_id}/plan-set")

    @mcp.tool(annotations=READ_ONLY)
    def get_availability(shoot_day_id: ShootDayId) -> dict:
        """배우 가용 시간과 주간 누적 근로시간, 계약서 문서 ID, 장소 이용과 허가 시간, 장비 가용 여부를 돌려준다."""
        return backend.request("GET", f"/internal/shoot-days/{shoot_day_id}/availability")

    @mcp.tool(annotations=READ_ONLY)
    def get_weather(shoot_day_id: ShootDayId) -> dict:
        """촬영일의 장소별 시간당 강수확률(%)을 돌려준다. 실내 장소인지도 함께 표시한다."""
        return backend.request("GET", f"/internal/shoot-days/{shoot_day_id}/weather")

    @mcp.tool(annotations=READ_ONLY)
    def get_disaster_alerts(shoot_day_id: ShootDayId) -> dict:
        """촬영일에 유효한 긴급재난문자(지역, 종류, 시작과 끝 시각, 내용)를 돌려준다. 없으면 alerts가 빈 목록이다."""
        # 빈 목록을 그대로 돌려주면 MCP 구조화 결과가 비어 모델에 null로 보이므로 이름 있는 필드로 감싼다.
        return {"alerts": backend.request("GET", f"/internal/shoot-days/{shoot_day_id}/disaster-alerts")}

    @mcp.tool(annotations=READ_ONLY)
    def search_locations(
        keywords: Annotated[list[str], Field(min_length=1, max_length=6, description="예: 실내, 자연광, 30평")],
        max_distance_km: Annotated[float, Field(gt=0, le=100)] = 40,
    ) -> dict:
        """아워플레이스 장소 카탈로그(시연용 mock)에서 키워드와 거리 조건에 맞는 대체 장소를 찾는다."""
        # 결과가 없을 때도 모델이 "찾은 장소 없음"으로 읽도록 빈 목록을 이름 있는 필드로 감싼다.
        found = backend.request(
            "GET",
            "/internal/locations/search",
            params={"keywords": ",".join(keywords), "maxDistanceKm": max_distance_km},
        )
        return {"locations": found}

    @mcp.tool(annotations=WRITE)
    def register_alternative_locations(
        shoot_day_id: ShootDayId,
        external_location_ids: Annotated[list[int], Field(min_length=1, max_length=3, description="search_locations 결과의 id")],
        keywords: Annotated[list[str], Field(min_length=1, max_length=6, description="1/2/3안에서 뽑은 장소 키워드")],
    ) -> dict:
        """아워플레이스 대체 장소를 촬영일의 4안 장소 후보로 등록한다. 등록한 뒤 evaluate_plans를 다시 부르면
        4안 장소가 1/2/3안의 장비, 시간대와 조합되어 같은 업무 규칙으로 평가된다. 업무 데이터를 바꾸는 도구다."""
        registered = backend.request(
            "POST",
            f"/internal/shoot-days/{shoot_day_id}/alternative-locations",
            json={"externalLocationIds": external_location_ids, "keywords": keywords},
        )
        return {"registered": registered}

    @mcp.tool(annotations=READ_ONLY)
    def evaluate_plans(
        shoot_day_id: ShootDayId,
        weights: Annotated[
            dict[str, float] | None,
            Field(description="최적화 가중치. 키: location, equipment, weather, budget, time, distance"),
        ] = None,
        extra_constraints: list[ExtraConstraint] | None = None,
        exclude_hashes: Annotated[list[str] | None, Field(description="이미 실패한 후보 해시")] = None,
    ) -> dict:
        """1/2/3안의 장소, 장비, 시간대를 요소 단위로 조합한 27개 후보를 업무 규칙 엔진으로 평가한다.
        하드 제약 위반 목록, 항목별 점수, 종합 점수, 비용을 돌려주며 실행 가능한 후보가 앞에 온다."""
        body: dict[str, Any] = {"shootDayId": shoot_day_id}
        if weights:
            body["weights"] = weights
        if extra_constraints:
            body["extraConstraints"] = [item.to_backend() for item in extra_constraints]
        if exclude_hashes:
            body["excludeHashes"] = exclude_hashes
        return backend.request("POST", "/internal/plans/evaluate", json=body)

    @mcp.tool(annotations=READ_ONLY)
    def validate_plan(
        shoot_day_id: ShootDayId,
        candidate: Candidate,
        data_version: Annotated[int, Field(ge=1)],
        extra_constraints: list[ExtraConstraint] | None = None,
    ) -> dict:
        """후보안 하나를 최신 데이터로 다시 검사한다. 데이터 버전이 바뀌었으면 stale=true를 돌려준다."""
        body = {
            "shootDayId": shoot_day_id,
            "candidate": candidate.to_backend(),
            "dataVersion": data_version,
            "extraConstraints": [item.to_backend() for item in extra_constraints or []],
        }
        return backend.request("POST", "/internal/plans/validate", json=body)

    @mcp.tool(annotations=READ_ONLY)
    def get_proposal(proposal_id: Annotated[int, Field(ge=1)]) -> dict:
        """변경안 하나의 원본 대비 변경, 점수, 체크리스트, 근거, 승인 현황을 돌려준다."""
        return backend.request("GET", f"/internal/proposals/{proposal_id}")

    @mcp.tool(annotations=WRITE)
    def submit_proposal(
        task_id: Annotated[int, Field(ge=1, description="backend 작업 ID")],
        event_id: Annotated[int, Field(ge=1)],
        shoot_day_id: ShootDayId,
        loop_no: Annotated[int, Field(ge=1)],
        candidate: Candidate,
        score: float,
        score_breakdown: dict[str, float],
        weights: dict[str, float],
        explanation: Annotated[str, Field(min_length=1, max_length=2000)],
        checklist: list[ChecklistItem],
        evidence: list[EvidenceItem],
        unresolved: list[str],
        data_version: Annotated[int, Field(ge=1)],
        review: Annotated[dict | None, Field(description="승인 요청 전 자체 검토 점수와 회차별 이력")] = None,
    ) -> dict:
        """최적안 1개를 변경안으로 등록하고 필수 승인자에게 승인 요청을 보낸다. 업무 데이터를 바꾸는 도구다."""
        body = {
            "taskId": task_id,
            "eventId": event_id,
            "shootDayId": shoot_day_id,
            "loopNo": loop_no,
            "candidate": candidate.to_backend(),
            "score": score,
            "scoreBreakdown": score_breakdown,
            "weights": weights,
            "explanation": explanation,
            "checklist": [
                {"constraint": c.constraint, "status": c.status, "note": c.note, "evidenceIds": c.evidence_ids} for c in checklist
            ],
            "evidence": [
                {"id": e.id, "docId": e.doc_id, "title": e.title, "text": e.text, "docType": e.doc_type} for e in evidence
            ],
            "unresolved": unresolved,
            "dataVersion": data_version,
            "review": review,
        }
        return backend.request("POST", "/internal/proposals", json=body)

    @mcp.tool(annotations=DESTRUCTIVE)
    def commit_plan(
        proposal_id: Annotated[int, Field(ge=1)],
        data_version: Annotated[int, Field(ge=1)],
    ) -> dict:
        """전원 승인된 변경안을 촬영 일정에 확정 반영하고 새 콜시트 버전을 만든다.
        데이터 버전이 다르면 VERSION_CONFLICT로 거부된다. 되돌릴 수 없는 변경 도구다."""
        return backend.request("POST", f"/internal/proposals/{proposal_id}/commit", json={"dataVersion": data_version})

    return mcp


def main() -> None:
    """compose 안에서 Streamable HTTP로 서버를 실행합니다."""
    server = build_server(BackendClient(BACKEND_URL, INTERNAL_TOKEN))
    server.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "9101")), path="/mcp")


if __name__ == "__main__":
    main()
