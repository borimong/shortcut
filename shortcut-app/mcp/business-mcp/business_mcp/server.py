"""business-mcp: 촬영 업무 기능을 Agent가 호출하는 MCP 도구로 공개한다.

- 도구 이름과 인자는 shortcut-app Agent가 부르는 이름(`business_` 접두어를 뗀 이름)과 같다.
- 모든 도구는 backend `/internal/**` API 하나에 1:1로 대응한다. 검증과 점수 계산은 Spring Boot
  제약·점수 엔진이 하고, 이 서버는 DB에 접근하지 않으며 규칙도 갖지 않는다.
- 조회 도구 10개, 쓰기 도구 3개(link_entity, register_alternative_locations, submit_proposal),
  되돌릴 수 없는 도구 1개(commit_plan).

실행:  python -m business_mcp.server        → http://0.0.0.0:9101/mcp (Streamable HTTP)
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
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

# ---------------------------------------------------------------- 공통 타입

NodeId = Annotated[
    str,
    Field(
        pattern=r"^[A-Z_]+:[A-Za-z0-9_\-]+$",
        description="온톨로지 노드 ID. 형식 TYPE:키 (예: SCENE:S12, ACTOR:1, LOCATION:2, BLOCK:1-PM, PLAN:1-2, SHOOT_DAY:1, CONTRACT:contract-actor-a-v3)",
    ),
]
ShootDayId = Annotated[int, Field(ge=1, description="촬영일 ID (시연 데이터는 1)")]
HourMinute = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$", description="HH:mm")]
DataVersion = Annotated[int, Field(ge=1, description="evaluate_plans 결과의 dataVersion")]


class ExtraConstraint(BaseModel):
    """승인자 거절 사유나 감독 지시에서 만든 추가 제약. 다음 평가부터 하드 제약으로 검사된다.
    REQUIRE_SETTING_MATCH는 대본의 실내/실외와 장소가 어긋나는 후보(예: 야외 장면을 실내 스튜디오에서)를 뺀다."""

    type: Literal[
        "EXCLUDE_LOCATION",
        "EXCLUDE_LOCATION_TIME",
        "EXCLUDE_EQUIPMENT",
        "MAX_EXTRA_COST",
        "REQUIRE_INDOOR",
        "LATEST_END",
        "EXCLUDE_TIME",
        "REQUIRE_SETTING_MATCH",
    ]
    location_id: int | None = Field(default=None, description="EXCLUDE_LOCATION, EXCLUDE_LOCATION_TIME")
    equipment_id: int | None = Field(default=None, description="EXCLUDE_EQUIPMENT")
    from_time: HourMinute | None = Field(default=None, description="EXCLUDE_LOCATION_TIME, EXCLUDE_TIME 시작")
    to_time: HourMinute | None = Field(default=None, description="EXCLUDE_LOCATION_TIME, EXCLUDE_TIME 끝")
    time: HourMinute | None = Field(default=None, description="LATEST_END 종료 한계 시각")
    amount: int | None = Field(default=None, ge=0, description="MAX_EXTRA_COST 상한(원)")
    reason: str = Field(default="", description="거절 사유 요약. 예: 성수 스튜디오 오후 공사 소음")
    source: str = Field(default="", description="사유를 낸 사람이나 문서. 예: 동시녹음팀장")

    def to_backend(self) -> dict[str, Any]:
        """backend 계약의 camelCase 필드로 바꾼다."""
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
    """변경 대상 블록의 후보안 하나."""

    location_id: int = Field(ge=1)
    equipment_ids: list[int] = Field(min_length=1)
    start: HourMinute
    end: HourMinute
    source: dict[str, int] | None = Field(
        default=None, description="요소별 출처 안 번호. 예: {location: 2, equipment: 1, time: 2}"
    )
    scene_order: list[str] | None = Field(
        default=None,
        description="오후 블록 씬 코드 순서. evaluate_plans 후보 sceneOrder의 code를 그대로 넣는다. 예: [S19, S18]. "
        "비우면 서버가 평가 때와 같은 방법으로 고른다",
    )

    def to_backend(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "locationId": self.location_id,
            "equipmentIds": sorted(self.equipment_ids),
            "start": self.start,
            "end": self.end,
        }
        if self.source:
            body["source"] = self.source
        if self.scene_order:
            body["sceneOrder"] = self.scene_order
        return body


class ChecklistItem(BaseModel):
    """하드 제약별 준수 확인 결과."""

    constraint: str
    status: Literal["PASS", "WARN"]
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """승인 화면 근거 패널에 보여 줄 조항. rag-mcp 검색 결과의 chunk_id·doc_id를 그대로 쓴다."""

    id: str
    doc_id: str
    title: str
    text: str
    doc_type: str = ""


# ---------------------------------------------------------------- 서버


def build_server(backend: BackendClient | None = None) -> FastMCP:
    """backend 클라이언트를 주입받아 도구를 등록한 서버를 만든다. 테스트는 MockTransport를 넘긴다."""
    backend = backend or BackendClient()
    mcp = FastMCP(
        "business-mcp",
        instructions=(
            "촬영 업무 데이터(온톨로지, 1/2/3안, 가용 자원, 날씨, 재난 문자, 계획 평가, 변경안 제출과 확정)를 다룹니다. "
            "조회 도구는 자유롭게 써도 되지만 link_entity, register_alternative_locations, submit_proposal은 "
            "업무 데이터를 바꾸고 commit_plan은 되돌릴 수 없습니다. 검증과 점수는 backend 엔진 결과를 그대로 쓰세요."
        ),
    )

    async def call(method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        try:
            return await backend.request(method, path, params=params, json=json)
        except BackendError as err:
            raise ToolError(to_tool_message(err)) from err

    # ---------------- 온톨로지

    @mcp.tool(annotations=READ_ONLY)
    async def get_entity_context(node_id: NodeId) -> dict:
        """온톨로지 노드 하나와 바로 연결된 이웃 노드(관계 이름, 방향 포함)를 돌려준다.
        배우의 현재 계약서 문서 ID, 씬과 장소, 예약 사이의 관계를 확인할 때 쓴다."""
        return await call("GET", f"/internal/ontology/nodes/{node_id}")

    @mcp.tool(annotations=READ_ONLY)
    async def find_impacted_entities(
        node_id: NodeId,
        depth: Annotated[int, Field(ge=1, le=3, description="탐색 깊이, 기본 2")] = 2,
        shoot_day_id: Annotated[
            int | None,
            Field(ge=1, description="이 촬영일의 노드만 따라간다. 주지 않으면 다른 촬영일 씬, 블록, 안까지 섞여 나온다"),
        ] = None,
    ) -> dict:
        """변경이 생긴 노드에서 depth 단계 안에 연결된 노드와 엣지를 모두 돌려준다.
        변경 영향 범위(관련 씬, 배우, 계약서, 예약, 장비)를 한 번에 볼 때 가장 먼저 쓴다.
        블록 노드(BLOCK:촬영일ID-블록코드)에서 시작하면 그 블록의 씬, 장소, 장비, 후보안(PLAN:촬영일ID-번호)이 depth 1에 나온다.
        배우와 장비는 여러 촬영일이 함께 쓰므로 재계획 중인 촬영일의 shoot_day_id를 넘겨 다른 촬영일 노드를 뺀다.
        결과는 엣지가 먼저, 노드는 시작점에서 가까운 순서다."""
        params: dict[str, Any] = {"nodeId": node_id, "depth": depth}
        if shoot_day_id is not None:
            params["shootDayId"] = shoot_day_id
        return await call("GET", "/internal/ontology/impact", params=params)

    @mcp.tool(annotations=WRITE)
    async def link_entity(
        src: NodeId,
        relation: Annotated[str, Field(min_length=1, max_length=20, description="관계 이름, 예: 촬영지, 사용, 출연")],
        dst: NodeId,
    ) -> dict:
        """두 온톨로지 노드 사이에 관계 엣지를 하나 추가한다. 업무 데이터를 바꾸는 도구다."""
        return await call("POST", "/internal/ontology/edges", json={"src": src, "relation": relation, "dst": dst})

    # ---------------- 촬영일 데이터

    @mcp.tool(annotations=READ_ONLY)
    async def get_plan_set(shoot_day_id: ShootDayId) -> dict:
        """변경 대상 블록의 씬과 배우, 현재 확정안, 제작사가 미리 만든 1/2/3안(장소, 장비, 시간대)을 돌려준다.
        씬마다 대본 분해 값이 있다: intExt(INT 실내, EXT 실외), timeOfDay(DAY, NIGHT), settingLocked(지정 세트에서만 촬영),
        characters(배역과 캐스팅된 배우 id), requirements(장비·소품·보조출연, level MUST 필수, WANT 선호).
        블록의 sunrise, sunset은 낮/밤 장면 판정에 쓰는 그날 일출과 일몰이다."""
        return await call("GET", f"/internal/shoot-days/{shoot_day_id}/plan-set")

    @mcp.tool(annotations=READ_ONLY)
    async def get_availability(shoot_day_id: ShootDayId) -> dict:
        """배우 가용 시간과 주간 누적 근로시간, 계약서 문서 ID, 장소 이용·허가 시간, 장비 가용 여부를 돌려준다.
        배우의 그날 실제 일정은 off(종일 불가), windows(가능 시간대), busy(다른 일정과 사유 종류)다.
        availableFrom~availableTo는 계약 기본 시간이고, 날짜별 일정과 변경 입력이 있으면 windows가 그보다 우선한다."""
        return await call("GET", f"/internal/shoot-days/{shoot_day_id}/availability")

    @mcp.tool(annotations=READ_ONLY)
    async def get_actor_schedule(
        shoot_day_id: ShootDayId,
        actor_ids: Annotated[list[int] | None, Field(description="볼 배우 id. 비우면 모든 배우")] = None,
        from_date: Annotated[
            str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="시작 날짜 YYYY-MM-DD. 비우면 이 촬영일 날짜")
        ] = None,
        days: Annotated[int, Field(ge=1, le=31, description="볼 날 수, 기본 14")] = 14,
    ) -> dict:
        """배우들의 날짜별 일정을 돌려준다. 날마다 off(종일 불가), windows(가능 시간대), busy(다른 작품, 광고나 행사,
        개인 일정, 이동 같은 사유 종류), shoots(우리 촬영에 배정된 블록과 씬)가 있다. 일정이 없는 날은 빠지고,
        그런 날은 계약 기본 시간(contractFrom~contractTo)에 촬영할 수 있다. 다른 날로 씬을 옮기거나 배우 일정을 물을 때 쓴다.
        개인 사정은 옮기지 않으려고 사유 종류만 준다."""
        params: dict[str, Any] = {"days": days}
        if actor_ids:
            params["actorIds"] = ",".join(str(i) for i in actor_ids)
        if from_date:
            params["from"] = from_date
        return await call("GET", f"/internal/shoot-days/{shoot_day_id}/actor-schedule", params=params)

    @mcp.tool(annotations=READ_ONLY)
    async def find_unplaceable_scenes(shoot_day_id: ShootDayId) -> dict:
        """아직 촬영 배정하지 않은 대본 씬마다 배우 날짜별 일정 안에서 찍을 수 있는 첫 날(firstDate)이나,
        어느 날에도 못 찍는 이유(reason)를 돌려준다. 예: 계약상 낮에만 되는 배우가 나오는 밤 야외 장면."""
        return await call("GET", f"/internal/shoot-days/{shoot_day_id}/unplaceable-scenes")

    @mcp.tool(annotations=READ_ONLY)
    async def get_weather(shoot_day_id: ShootDayId) -> dict:
        """촬영일의 장소별 시간당 강수량(mm)과 촬영 불가 기준(rainBlockMm)을 돌려준다. 실내 장소인지도 함께 표시한다.
        장소마다 forecast에 예보 출처(LIVE 날씨 API, SEED 시연용 고정, NONE 실시간 예보를 아직 못 받아 강수량 없음)와
        갱신 시각(updatedAt)이 있다. manual이 true면 사람이 변경 입력으로 넣은 강수량이 예보보다 우선 반영된 것이다."""
        return await call("GET", f"/internal/shoot-days/{shoot_day_id}/weather")

    @mcp.tool(annotations=READ_ONLY)
    async def get_disaster_alerts(shoot_day_id: ShootDayId) -> dict:
        """촬영일에 유효한 긴급재난문자(지역, 종류, 시작·끝 시각, 내용)를 돌려준다. 없으면 alerts가 빈 목록이다."""
        # 빈 목록을 그대로 돌려주면 구조화 결과가 비어 모델에 null로 보이므로 이름 있는 필드로 감싼다.
        return {"alerts": await call("GET", f"/internal/shoot-days/{shoot_day_id}/disaster-alerts")}

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    async def search_locations(
        keywords: Annotated[list[str], Field(min_length=1, max_length=6, description="예: 실내, 자연광, 30평")],
        max_distance_km: Annotated[float, Field(gt=0, le=100)] = 40,
    ) -> dict:
        """아워플레이스 장소 카탈로그(시연용 mock)에서 키워드와 거리 조건에 맞는 대체 장소를 찾는다.
        1/2/3안이 모두 불가능할 때 4안 장소를 찾는 데 쓴다."""
        found = await call(
            "GET",
            "/internal/locations/search",
            params={"keywords": ",".join(keywords), "maxDistanceKm": max_distance_km},
        )
        return {"locations": found}

    @mcp.tool(annotations=WRITE)
    async def register_alternative_locations(
        shoot_day_id: ShootDayId,
        external_location_ids: Annotated[
            list[int], Field(min_length=1, max_length=3, description="search_locations 결과의 id")
        ],
        keywords: Annotated[list[str], Field(min_length=1, max_length=6, description="1/2/3안에서 뽑은 장소 키워드")],
    ) -> dict:
        """아워플레이스 대체 장소를 촬영일의 4안 장소 후보로 등록한다. 등록한 뒤 evaluate_plans를 다시 부르면
        4안 장소가 1/2/3안의 장비, 시간대와 조합되어 같은 업무 규칙으로 평가된다. 업무 데이터를 바꾸는 도구다."""
        registered = await call(
            "POST",
            f"/internal/shoot-days/{shoot_day_id}/alternative-locations",
            json={"externalLocationIds": external_location_ids, "keywords": keywords},
        )
        return {"registered": registered}

    # ---------------- 계획 평가 (backend 제약·점수 엔진)

    @mcp.tool(annotations=READ_ONLY)
    async def evaluate_plans(
        shoot_day_id: ShootDayId,
        weights: Annotated[
            dict[str, float] | None,
            Field(description="최적화 가중치. 키: location, equipment, weather, budget, time, distance. 지시가 없으면 비운다"),
        ] = None,
        extra_constraints: list[ExtraConstraint] | None = None,
        exclude_hashes: Annotated[list[str] | None, Field(description="이미 실패한 후보 해시")] = None,
    ) -> dict:
        """1/2/3안의 장소, 장비, 시간대를 요소 단위로 조합한 27개 후보를 업무 규칙 엔진으로 평가한다.
        하드 제약 위반 목록, 항목별 점수, 종합 점수, 비용, dataVersion을 돌려주며 실행 가능한 후보가 앞에 온다.
        예산 한도 같은 하드 제약은 가중치와 상관없이 유지된다.
        후보마다 sceneOrder(씬별 시작·끝 시각)가 있다. 배우 일정이나 해 때문에 지금 순서로 막히면 엔진이 블록 안
        씬 순서를 바꾸고 sceneOrderChanged=true로 표시한다. 이 순서를 validate_plan, submit_proposal에 그대로 넘긴다."""
        body: dict[str, Any] = {"shootDayId": shoot_day_id}
        if weights:
            body["weights"] = weights
        if extra_constraints:
            body["extraConstraints"] = [item.to_backend() for item in extra_constraints]
        if exclude_hashes:
            body["excludeHashes"] = exclude_hashes
        return await call("POST", "/internal/plans/evaluate", json=body)

    @mcp.tool(annotations=READ_ONLY)
    async def validate_plan(
        shoot_day_id: ShootDayId,
        candidate: Candidate,
        data_version: DataVersion,
        extra_constraints: list[ExtraConstraint] | None = None,
    ) -> dict:
        """후보안 하나를 최신 데이터로 다시 검사한다. 데이터 버전이 바뀌었으면 stale=true를 돌려준다.
        submit_proposal 직전에 부른다. candidate.scene_order를 주면 그 씬 순서 그대로 검사하고, 판정에 쓴 씬 시각표를
        sceneOrder로 돌려준다."""
        body = {
            "shootDayId": shoot_day_id,
            "candidate": candidate.to_backend(),
            "dataVersion": data_version,
            "extraConstraints": [item.to_backend() for item in extra_constraints or []],
        }
        return await call("POST", "/internal/plans/validate", json=body)

    # ---------------- 변경안

    @mcp.tool(annotations=READ_ONLY)
    async def get_proposal(proposal_id: Annotated[int, Field(ge=1)]) -> dict:
        """변경안 하나의 원본 대비 변경, 점수, 체크리스트, 근거, 승인 현황을 돌려준다."""
        return await call("GET", f"/internal/proposals/{proposal_id}")

    @mcp.tool(annotations=WRITE)
    async def submit_proposal(
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
        data_version: DataVersion,
        review: Annotated[dict | None, Field(description="승인 요청 전 자체 검토 점수와 회차별 이력")] = None,
    ) -> dict:
        """최적안 1개를 변경안으로 등록하고 필수 승인자에게 승인 요청을 보낸다. 업무 데이터를 바꾸는 도구다.
        backend가 저장 직전에 한 번 더 검증하므로 위반이 있으면 PLAN_INVALID로 거부된다.
        씬 순서가 바뀐 후보는 candidate.scene_order에 그 순서를 넣는다. 씬 순서가 바뀌면 조감독 승인이 붙는다."""
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
                {"constraint": c.constraint, "status": c.status, "note": c.note, "evidenceIds": c.evidence_ids}
                for c in checklist
            ],
            "evidence": [
                {"id": e.id, "docId": e.doc_id, "title": e.title, "text": e.text, "docType": e.doc_type} for e in evidence
            ],
            "unresolved": unresolved,
            "dataVersion": data_version,
            "review": review,
        }
        return await call("POST", "/internal/proposals", json=body)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def commit_plan(
        proposal_id: Annotated[int, Field(ge=1)],
        data_version: DataVersion,
    ) -> dict:
        """전원 승인된 변경안을 촬영 일정에 확정 반영하고 새 콜시트 버전을 만든다.
        데이터 버전이 다르면 VERSION_CONFLICT, 승인이 덜 끝났으면 NOT_APPROVED로 거부된다. 되돌릴 수 없는 도구다."""
        return await call("POST", f"/internal/proposals/{proposal_id}/commit", json={"dataVersion": data_version})

    return mcp


# 예전 이름 (rc2 코드와 테스트 호환)
create_server = build_server


def main() -> None:
    """compose 안에서 Streamable HTTP로 실행한다."""
    server = build_server(BackendClient())
    server.run(
        transport="http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "9101")),
        path="/mcp",
    )


if __name__ == "__main__":
    main()
