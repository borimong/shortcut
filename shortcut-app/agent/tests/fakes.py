"""그래프 테스트용 가짜 LLM, 가짜 MCP 서버, 이벤트 수집기입니다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.config import Limits, Settings
from app.graph.schemas import (
    AlternativeKeywords,
    ConstraintFinding,
    ConstraintItem,
    ConstraintSet,
    ImpactSummary,
    PlanExplanation,
    PlanReview,
    RejectionPlan,
    WeightAdjustment,
)
from app.graph.state import HARD_CONSTRAINTS
from app.harness.tools import ToolGateway
from app.runtime import RunContext

EVIDENCE_BY_CONSTRAINT = {
    "CONTRACT": (
        "contract-actor-a-v3#3",
        "contract-actor-a-v3",
        "배우 A 출연 계약서 v3",
        "제6조 야간 촬영",
        "22시 이후의 촬영은 하지 않는다.",
        "CONTRACT",
    ),
    "SCHEDULE": (
        "contract-actor-a-v3#1",
        "contract-actor-a-v3",
        "배우 A 출연 계약서 v3",
        "제5조 촬영 시간",
        "가용 시간은 09시부터 16시까지이다.",
        "CONTRACT",
    ),
    "LAW": (
        "law-labor-standards#2",
        "law-labor-standards",
        "근로기준법 요약",
        "제53조 연장 근로의 제한",
        "1주 근로시간의 상한은 52시간이다.",
        "LAW",
    ),
    "BUDGET": (
        "budget-approval-policy#1",
        "budget-approval-policy",
        "제작비 규정",
        "블록 예산 상한",
        "합계는 100만원을 넘을 수 없다.",
        "POLICY",
    ),
    "NO_FLY_ZONE": (
        "no-fly-zone-notice#2",
        "no-fly-zone-notice",
        "드론 비행 안내",
        "휴전선 인근 비행금지구역",
        "파주 세트장은 비행금지구역 안에 있다.",
        "NO_FLY",
    ),
    "DISASTER": (
        "safety-disaster-weather#1",
        "safety-disaster-weather",
        "안전 지침",
        "긴급재난문자 수신 시 원칙",
        "해당 시간대의 그 지역 촬영은 하지 않는다.",
        "SAFETY",
    ),
    "WEATHER": (
        "safety-disaster-weather#2",
        "safety-disaster-weather",
        "안전 지침",
        "강수확률에 따른 야외 촬영 판단",
        "70퍼센트 이상이면 제외한다.",
        "SAFETY",
    ),
    "SCRIPT": (
        "script-ep07-v1#13",
        "script-ep07-v1",
        "드라마 숏컷 7화 「봄, 봄」 대본 1고",
        "S#12. 한강 공원 산책로 (낮, 실외)",
        "강바람. 텀블러 두 개를 든 도현과 지우가 나란히 걷는다.",
        "SCRIPT",
    ),
}


def make_settings(**limit_overrides) -> Settings:
    limits = Limits(**limit_overrides)
    return Settings(
        backend_url="http://backend",
        internal_token="t",
        business_mcp_url="http://b/mcp",
        rag_mcp_url="http://r/mcp",
        rabbitmq_url="amqp://x",
        checkpoint_dsn="postgresql://x",
        openai_model="gpt-4o-mini",
        fallback_model="gpt-4.1-mini",
        limits=limits,
        tool_timeout_seconds=5,
        tool_result_max_chars=4000,
        context_token_budget=6000,
        langsmith_project=None,
    )


def _candidate(loc_id, loc_name, loc_opt, eq_opt, eq_items, t_opt, start, end, score, feasible=True, indoor=True):
    eq_ids = ",".join(str(i["id"]) for i in eq_items)
    return {
        "hash": f"L{loc_id}-E{eq_ids}-T{start.replace(':', '')}{end.replace(':', '')}",
        "location": {"optionNo": loc_opt, "id": loc_id, "name": loc_name, "indoor": indoor},
        "equipment": {"optionNo": eq_opt, "items": eq_items},
        "time": {"optionNo": t_opt, "start": start, "end": end},
        "feasible": feasible,
        "violations": []
        if feasible
        else [{"code": "RAIN_HARD", "constraint": "WEATHER", "message": "강수확률 80", "ruleRef": "WEATHER_RAIN"}],
        "warnings": [],
        "softScores": {"location": 0.8, "equipment": 1.0, "weather": 1.0, "budget": 0.55, "time": 0.5, "distance": 0.72},
        "totalScore": score,
        "cost": 450000,
        "extraCost": 150000,
        "distanceKm": 14,
    }


SEONGSU = _candidate(
    2,
    "성수 스튜디오",
    2,
    1,
    [{"id": 1, "name": "카메라 패키지 A"}, {"id": 2, "name": "드론"}, {"id": 3, "name": "반사판"}],
    2,
    "14:00",
    "16:00",
    0.79,
)
SEONGSU_MORNING = _candidate(
    2,
    "성수 스튜디오",
    2,
    1,
    [{"id": 1, "name": "카메라 패키지 A"}, {"id": 2, "name": "드론"}, {"id": 3, "name": "반사판"}],
    3,
    "10:00",
    "12:00",
    0.75,
)
PAJU = _candidate(
    3, "파주 세트장", 3, 3, [{"id": 1, "name": "카메라 패키지 A"}, {"id": 5, "name": "짐벌 세트"}], 2, "14:00", "16:00", 0.6
)
ILSAN = _candidate(
    101,
    "일산 실내 스튜디오",
    4,
    1,
    [{"id": 1, "name": "카메라 패키지 A"}, {"id": 2, "name": "드론"}, {"id": 3, "name": "반사판"}],
    1,
    "13:00",
    "15:00",
    0.66,
)
HANGANG = _candidate(
    1, "한강 공원", 1, 1, [{"id": 1, "name": "카메라 패키지 A"}], 1, "13:00", "15:00", 0.7, feasible=False, indoor=False
)


@dataclass
class FakeBackendState:
    """가짜 business-mcp가 공유하는 업무 상태입니다."""

    proposals: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    evaluate_calls: list[dict] = field(default_factory=list)
    validate_violations: list[str] = field(default_factory=list)
    commit_conflicts: int = 0
    submit_conflicts: int = 0
    registered: list = field(default_factory=list)
    no_feasible: bool = False
    # 모델이 거절 사유를 좁은 제약으로 바꾼 상황을 흉내 내려고 추가 제약을 무시하고 성수 오전 후보를 넣는다.
    narrow_constraints: bool = False
    # 엔진이 상위 후보 몇 개만 돌려주는 상황을 흉내 낸다.
    top_k: int | None = None
    # 아워플레이스 검색 결과가 없는 상황
    no_alternatives: bool = False


class FakeMcpClient:
    """fastmcp Client와 같은 메서드(list_tools, call_tool, read_resource)를 가진 가짜입니다."""

    def __init__(self, prefix: str, backend: FakeBackendState):
        self.prefix = prefix
        self.backend = backend
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        names = BUSINESS_TOOLS if self.prefix == "business" else RAG_TOOLS
        return [
            SimpleNamespace(name=n, description=f"{n} 설명", input_schema={"type": "object", "properties": {}}) for n in names
        ]

    async def read_resource(self, uri: str):
        doc_id = uri.rsplit("/", 1)[-1]
        text = " ".join(e[4] for e in EVIDENCE_BY_CONSTRAINT.values() if e[1] == doc_id)
        return [SimpleNamespace(text=f"# 원문\n{text}")]

    async def call_tool(self, name: str, args: dict, raise_on_error: bool = True):
        self.calls.append((name, args))
        handler = getattr(self, f"_{name}")
        try:
            data = handler(args)
        except FakeToolError as error:
            return SimpleNamespace(is_error=True, content=[SimpleNamespace(text=str(error))], structured_content=None, data=None)
        structured = data if isinstance(data, dict) else {"result": data}
        return SimpleNamespace(is_error=False, content=[], structured_content=structured, data=data)

    def _get_plan_set(self, args):
        return {
            "shootDayId": 1,
            "dataVersion": 1,
            "block": {"code": "PM", "durationMin": 120, "scenes": [{"code": "S12"}, {"code": "S13"}], "actorIds": [1, 2]},
            "current": {
                "location": {"id": 1, "name": "한강 공원"},
                "equipment": [{"id": 1}],
                "start": "13:00",
                "end": "15:00",
                "cost": 300000,
            },
            "options": [{"optionNo": 1}, {"optionNo": 2}, {"optionNo": 3}],
        }

    def _get_availability(self, args):
        return {
            "actors": [
                {"id": 1, "name": "배우 A", "contractDocId": "contract-actor-a-v3"},
                {"id": 2, "name": "배우 B", "contractDocId": "contract-actor-b-v1"},
                {"id": 3, "name": "배우 C", "contractDocId": "contract-actor-c-v2"},
            ],
            "locations": [],
            "equipment": [],
            "crewWeeklyHoursUsed": 40,
            "managerPhone": "010-2481-7731",
        }

    def _get_weather(self, args):
        return {"date": "2026-10-21", "locations": [{"locationId": 1, "hourly": [{"hour": 13, "precipProb": 80}]}]}

    def _get_disaster_alerts(self, args):
        return {"alerts": []}

    def _find_impacted_entities(self, args):
        return {"root": args["node_id"], "nodes": [{"nodeId": "SCENE:S12"}, {"nodeId": "ACTOR:1"}], "edges": []}

    def _get_entity_context(self, args):
        return {"node": {"nodeId": args["node_id"]}, "neighbors": []}

    def _evaluate_plans(self, args):
        self.backend.evaluate_calls.append(args)
        if self.backend.no_feasible:
            return {"dataVersion": 1, "weights": args["weights"], "feasibleCount": 0, "candidates": [HANGANG]}
        if self.backend.narrow_constraints:
            excluded = set()
            ranked = [SEONGSU, SEONGSU_MORNING, PAJU]
        else:
            excluded = {c.get("location_id") for c in args.get("extra_constraints") or []}
            ranked = [c for c in (SEONGSU, PAJU) if c["location"]["id"] not in excluded]
        ranked += [ILSAN] if self.backend.registered and 101 not in excluded else []
        ranked += [HANGANG]
        ranked = [c for c in ranked if c["hash"] not in (args.get("exclude_hashes") or [])]
        if self.backend.top_k:
            ranked = ranked[: self.backend.top_k]
        return {
            "dataVersion": 1,
            "weights": args["weights"],
            "feasibleCount": sum(c["feasible"] for c in ranked),
            "candidates": ranked,
        }

    def _validate_plan(self, args):
        candidate = args["candidate"]
        if self.backend.validate_violations:
            code = self.backend.validate_violations.pop(0)
            return {"valid": False, "stale": False, "dataVersion": 1, "violations": [{"code": code}], "warnings": []}
        assert candidate["location_id"] in {2, 3, 101}
        return {"valid": True, "stale": False, "dataVersion": 1, "violations": [], "warnings": []}

    def _submit_proposal(self, args):
        if self.backend.submit_conflicts:
            self.backend.submit_conflicts -= 1
            raise FakeToolError("[VERSION_CONFLICT] 데이터 버전이 다릅니다. (retryable=false)")
        proposal_id = len(self.backend.proposals) + 10
        self.backend.proposals.append({"id": proposal_id, **args})
        return {
            "proposalId": proposal_id,
            "versionNo": f"v{len(self.backend.proposals) + 1}",
            "requiredApprovers": ["DIRECTOR", "AD1", "SOUND"],
            "status": "PENDING",
        }

    def _commit_plan(self, args):
        if self.backend.commit_conflicts:
            self.backend.commit_conflicts -= 1
            raise FakeToolError("[VERSION_CONFLICT] 데이터 버전이 다릅니다. (retryable=false)")
        self.backend.commits.append(args)
        return {"callsheetVersionNo": 2, "reservationStatus": "MANUAL_PENDING", "distributed": False}

    def _register_alternative_locations(self, args):
        self.backend.registered.extend(args["external_location_ids"])
        registered = [
            {"locationId": 100 + i, "externalId": i, "name": "일산 실내 스튜디오", "fit": 0.8}
            for i in args["external_location_ids"]
        ]
        return {"registered": registered}

    def _search_locations(self, args):
        if self.backend.no_alternatives:
            return {"locations": []}
        return {"locations": [{"id": 1, "name": "일산 실내 스튜디오", "distanceKm": 25, "source": "OURPLACE_MOCK"}]}

    def _get_proposal(self, args):
        return {"id": args["proposal_id"], "proposed": {"location": {"name": "성수 스튜디오"}}}

    def _search_regulation(self, args):
        return [_hit(c) for c in HARD_CONSTRAINTS if EVIDENCE_BY_CONSTRAINT[c][5] not in ("CONTRACT", "SCRIPT")]

    def _search_script(self, args):
        return [_hit("SCRIPT")]

    def _get_actor_schedule(self, args):
        return {"from": "2026-10-22", "to": "2026-11-04", "actors": []}

    def _find_unplaceable_scenes(self, args):
        return {"from": "2026-10-22", "to": "2027-01-21", "scenes": []}

    def _search_contract_clause(self, args):
        return [_hit(c) for c in ("CONTRACT", "SCHEDULE") if EVIDENCE_BY_CONSTRAINT[c][1] == args["contract_doc_id"]]


class FakeToolError(Exception):
    pass


BUSINESS_TOOLS = [
    "get_entity_context",
    "find_impacted_entities",
    "link_entity",
    "get_plan_set",
    "get_availability",
    "get_weather",
    "get_disaster_alerts",
    "get_actor_schedule",
    "find_unplaceable_scenes",
    "search_locations",
    "register_alternative_locations",
    "evaluate_plans",
    "validate_plan",
    "get_proposal",
    "submit_proposal",
    "commit_plan",
]
RAG_TOOLS = ["search_regulation", "search_contract_clause", "search_script", "index_document", "delete_document"]


def _hit(constraint: str) -> dict:
    chunk_id, doc_id, title, heading, text, doc_type = EVIDENCE_BY_CONSTRAINT[constraint]
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "title": title,
        "heading": heading,
        "text": text,
        "doc_type": doc_type,
        "version": "v",
        "score": 0.9,
    }


class FakeModel:
    """노드 프롬프트의 첫 줄을 보고 정해진 행동을 돌려주는 가짜 LLM입니다."""

    def __init__(self, *, cite_evidence: bool = True, review_scores=None, review_actions=None, explanation_extras=None):
        self.cite_evidence = cite_evidence
        # 설명을 쓸 때마다 하나씩 덧붙일 문장이다. 선택하지 않은 장비 이름을 넣어 설명 검사를 시험한다.
        self.explanation_extras = list(explanation_extras or [])
        # 자체 검토 회차마다 돌려줄 총점과 행동이다. 다 쓰면 마지막 값을 반복한다.
        self.review_scores = list(review_scores or [90])
        self.review_actions = list(review_actions or ["REWRITE"])
        self.structured_calls: list[str] = []
        self.impact_prompts: list[str] = []

    async def chat(self, ctx: RunContext, messages, tools=None) -> AIMessage:
        ctx.counter["llm_calls"] += 1
        task = _task_line(messages)
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="조사를 마쳤습니다.")
        if "변경 영향 분석" in task:
            self.impact_prompts.append(str(next(m for m in messages if isinstance(m, HumanMessage)).content))
            return _tool_calls(
                ("business_find_impacted_entities", {"node_id": "SCENE:S12", "depth": 2, "shoot_day_id": 1}),
                ("business_get_weather", {"shoot_day_id": 1}),
            )
        if "하드 제약 근거 수집" in task:
            return _tool_calls(
                ("rag_search_regulation", {"query": "주 52시간"}),
                ("rag_search_contract_clause", {"query": "야간 촬영", "contract_doc_id": "contract-actor-a-v3"}),
                ("rag_search_script", {"query": "변경 대상 씬", "scene_codes": ["S12", "S13"]}),
            )
        if "근거 조회" in task:
            return _tool_calls(("rag_search_regulation", {"query": "강수확률"}), ("business_get_proposal", {"proposal_id": 10}))
        return AIMessage(content="")

    async def structured(self, ctx: RunContext, messages, schema):
        ctx.counter["llm_calls"] += 1
        self.structured_calls.append(schema.__name__)
        text = "\n".join(str(m.content) for m in messages)
        ids = re.findall(r"\[([a-z0-9\-]+#\d+)\]", text)
        if schema is ImpactSummary:
            return ImpactSummary(focus_nodes=["SCENE:S12"], impacted=[], risks=["13시 이후 우천"])
        if schema is ConstraintSet:
            by_constraint = {c: EVIDENCE_BY_CONSTRAINT[c][0] for c in HARD_CONSTRAINTS}
            return ConstraintSet(
                findings=[
                    ConstraintFinding(
                        constraint=c, summary="적용", evidence_ids=[by_constraint[c]] if by_constraint[c] in ids else []
                    )
                    for c in HARD_CONSTRAINTS
                ]
            )
        if schema is WeightAdjustment:
            return WeightAdjustment(
                location=0.5, equipment=0.15, weather=0.2, budget=0.0, time=0.1, distance=0.15, rationale="품질 우선"
            )
        if schema is PlanExplanation:
            checklist = [
                {
                    "constraint": c,
                    "status": "PASS",
                    "note": "준수",
                    "evidence_ids": [EVIDENCE_BY_CONSTRAINT[c][0]] if self.cite_evidence else [],
                }
                for c in HARD_CONSTRAINTS
            ]
            chosen = re.search(r"## 선택한 후보\n장소 (.+?)\(", text).group(1)
            extra = self.explanation_extras.pop(0) if self.explanation_extras else ""
            return PlanExplanation(
                explanation=f"우천으로 {chosen}로 옮깁니다. {extra}".strip(),
                checklist=checklist,
                unresolved=["예약 확정"],
                needs_more_info=False,
            )
        if schema is RejectionPlan:
            location_id = int(re.search(r"장소 ID (\d+)", text).group(1))
            if location_id == 2:
                item = ConstraintItem(type="EXCLUDE_LOCATION_TIME", location_id=2, from_time="13:00", to_time="18:00")
            else:
                item = ConstraintItem(type="EXCLUDE_LOCATION", location_id=location_id)
            return RejectionPlan(constraints=[item], summary=f"장소 {location_id}을 빼고 다시 짭니다")
        if schema is PlanReview:
            score = self.review_scores.pop(0) if len(self.review_scores) > 1 else self.review_scores[0]
            action = self.review_actions.pop(0) if len(self.review_actions) > 1 else self.review_actions[0]
            each, rest = divmod(score, 5)
            parts = [each + (1 if i < rest else 0) for i in range(5)]
            return PlanReview(
                evidence=parts[0],
                rejection=parts[1],
                optimization=parts[2],
                explanation=parts[3],
                risk=parts[4],
                feedback=[f"{score}점 피드백"],
                action=action,
            )
        if schema is AlternativeKeywords:
            return AlternativeKeywords(keywords=["실내", "자연광"], max_distance_km=40)
        raise AssertionError(schema)

    async def stream_text(self, ctx: RunContext, messages) -> str:
        ctx.counter["llm_calls"] += 1
        answer = "실내로 옮긴 이유는 강수확률 기준 때문입니다 [safety-disaster-weather#2]."
        for word in answer.split(" "):
            await ctx.events.publish("TOKEN", {"text": word + " "})
        return answer


def _task_line(messages) -> str:
    human = next(m for m in messages if isinstance(m, HumanMessage))
    return str(human.content).splitlines()[0]


def _tool_calls(*calls) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"call-{i}"} for i, (n, a) in enumerate(calls)])


class EventLog:
    def __init__(self):
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]


def make_context(backend: FakeBackendState | None = None, *, model: FakeModel | None = None, **limit_overrides):
    backend = backend or FakeBackendState()
    settings = make_settings(**limit_overrides)
    clients = {"business": FakeMcpClient("business", backend), "rag": FakeMcpClient("rag", backend)}
    tools = ToolGateway(clients, timeout_seconds=5, max_chars=4000, max_same_calls=settings.limits.max_same_tool_calls)
    events = EventLog()
    ctx = RunContext("task-1", "trace-1", settings, model or FakeModel(), tools, events)
    return ctx, backend, clients, events
