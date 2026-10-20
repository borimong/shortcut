"""mock backend: Spring Boot `/internal/**`를 흉내 내는 개발용 서버 (계약 rc2, contracts/openapi-internal.yaml).

D(business-mcp)와 E(Agent)가 B·C를 기다리지 않고 개발·테스트하기 위해 쓴다.
제약·점수 계산은 engine.py(참조 구현)를 그대로 쓴다. 실제 backend는 C가 같은 규칙을 Java로 구현한다.

실행:  uvicorn mock_backend.app:app --port 8080
"""
from __future__ import annotations

import copy
import itertools
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import engine as eng
from . import fixtures as fx

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "dev-internal-token")
ENTITY_TYPES = ("ACTOR", "SCENE", "BLOCK", "LOCATION", "EQUIPMENT", "CONTRACT", "BOOKING", "PLAN_SET", "REGULATION", "PERSON")
EVENT_TYPES = ("WEATHER", "ACTOR_SCHEDULE", "LOCATION_CANCELLED", "EQUIPMENT_FAILURE")


# ---------------------------------------------------------------- 상태


class State:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.blocks = copy.deepcopy(fx.BLOCKS)
        self.schedule_version = fx.BASE_SCHEDULE_VERSION
        self.data_version = fx.BASE_SCHEDULE_VERSION
        self.candidates: dict[str, dict] = {}
        self.plans: dict[int, dict] = {}
        self.plan_ids = itertools.count(801)
        self.plan_versions = itertools.count(fx.BASE_SCHEDULE_VERSION + 1)
        self.bookings: dict[str, dict] = {}
        self.booking_ids = itertools.count(1)
        self.links: list[dict] = []
        self.idempotency: dict[str, Any] = {}
        self.outbox: list[dict] = []
        self.events: list[dict] = []


STATE = State()


# ---------------------------------------------------------------- 공통


def error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse({"code": code, "message": message, "details": details or {}}, status_code=status)


def check_auth(request: Request, *, change: bool = False) -> JSONResponse | None:
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        return error(401, "UNAUTHORIZED", "X-Internal-Token이 없거나 틀렸다")
    missing = [h for h in ("X-User-Id", "X-User-Role", "X-Project-Id", "X-Task-Id") if not request.headers.get(h)]
    if missing:
        return error(400, "VALIDATION_ERROR", f"{', '.join(missing)} 헤더가 없다", {"fields": missing})
    if request.headers["X-User-Role"] not in fx.ROLES:
        return error(400, "VALIDATION_ERROR", f"알 수 없는 역할 {request.headers['X-User-Role']}", {"fields": ["X-User-Role"]})
    if change and request.headers["X-User-Role"] not in fx.CHANGE_REQUEST_ROLES:
        return error(403, "FORBIDDEN", "변경은 제작실장, 1조감독, 2조감독만 요청할 수 있다",
                     {"allowedRoles": sorted(fx.CHANGE_REQUEST_ROLES)})
    return None


async def body(request: Request) -> dict:
    raw = await request.body()
    return (await request.json()) if raw else {}


def cached(request: Request):
    key = request.headers.get("Idempotency-Key")
    return key, (STATE.idempotency.get(key) if key else None)


def windows(ws) -> list[dict]:
    return [{"start": s, "end": e} for s, e in ws]


def actor_ids_of(block: dict) -> list[str]:
    return sorted({a for s in block["sceneIds"] for a in fx.SCENES[s]["actorIds"]})


# ---------------------------------------------------------------- 온톨로지


def node(t: str, i: str) -> dict | None:
    if t == "ACTOR" and i in fx.ACTORS:
        a = fx.ACTORS[i]
        return {"type": t, "id": i, "label": a["name"], "attrs": {"available": windows(a["available"]), "weeklyHoursSoFar": a["weeklyHoursSoFar"]}}
    if t == "SCENE" and i in fx.SCENES:
        s = fx.SCENES[i]
        return {"type": t, "id": i, "label": s["title"], "attrs": {"intent": s["intent"], "durationMin": s["durationMin"]}}
    if t == "BLOCK":
        b = next((b for b in STATE.blocks if b["blockId"] == i), None)
        return b and {"type": t, "id": i, "label": f"{b['blockId']} {b['start']}~{b['end']}", "attrs": {"start": b["start"], "end": b["end"]}}
    if t == "LOCATION" and i in fx.LOCATIONS:
        loc = fx.LOCATIONS[i]
        return {"type": t, "id": i, "label": loc["name"], "attrs": {"outdoor": loc["outdoor"], "available": windows(loc["available"]), "droneProhibited": loc["droneProhibited"]}}
    if t == "EQUIPMENT" and i in fx.EQUIPMENT:
        return {"type": t, "id": i, "label": fx.EQUIPMENT[i]["name"], "attrs": {"available": windows(fx.EQUIPMENT[i]["available"])}}
    if t == "CONTRACT" and i in fx.CONTRACTS:
        c = fx.CONTRACTS[i]
        return {"type": t, "id": i, "label": f"{fx.ACTORS[c['actorId']]['name']} 출연 계약서 v{c['version']}", "attrs": {"version": c["version"], "status": c["status"], "docId": c["docId"]}}
    if t == "BOOKING" and i == "R-2031":
        return {"type": t, "id": i, "label": "성수 스튜디오 예약 R-2031", "attrs": {"platform": "아워플레이스", "start": "16:30", "end": "18:30", "status": "PAID"}}
    if t == "PLAN_SET" and i in fx.PLAN_SETS:
        return {"type": t, "id": i, "label": f"{i} 1/2/3안", "attrs": {"plans": list(fx.PLAN_SETS[i]["plans"])}}
    if t == "REGULATION" and i in ("law-labor", "permit-hangang", "zone-paju", "guide-contract"):
        return {"type": t, "id": i, "label": i, "attrs": {"docId": i}}
    if t == "PERSON" and i.isdigit() and int(i) in fx.USERS:
        u = fx.USERS[int(i)]
        return {"type": t, "id": i, "label": u["name"], "attrs": {"role": u["role"], "roleName": fx.ROLES[u["role"]]}}
    return None


def edges() -> list[dict]:
    e: list[dict] = []

    def add(ft, fi, rel, tt, ti, attrs=None):
        e.append({"from": (ft, fi), "relation": rel, "to": (tt, ti), "attrs": attrs or {}})

    for aid, a in fx.ACTORS.items():
        c = fx.CONTRACTS[a["contractDocId"]]
        add("ACTOR", aid, "HAS_CONTRACT", "CONTRACT", c["docId"], {"version": c["version"], "status": c["status"]})
    add("CONTRACT", "contract-A04-v3", "SUPERSEDES", "CONTRACT", "contract-A04-v2")
    for sid, s in fx.SCENES.items():
        for aid in s["actorIds"]:
            add("ACTOR", aid, "APPEARS_IN", "SCENE", sid)
    for u in fx.USERS.values():
        for aid in u.get("managedActorIds", []):
            add("ACTOR", aid, "MANAGED_BY", "PERSON", str(u["id"]))
    for b in STATE.blocks:
        for sid in b["sceneIds"]:
            add("SCENE", sid, "IN_BLOCK", "BLOCK", b["blockId"])
        add("BLOCK", b["blockId"], "SHOT_AT", "LOCATION", b["locationId"], {"start": b["start"], "end": b["end"]})
        for eq in b["equipmentIds"]:
            add("BLOCK", b["blockId"], "USES", "EQUIPMENT", eq)
        if b["blockId"] in fx.PLAN_SETS:
            add("BLOCK", b["blockId"], "HAS_PLAN_SET", "PLAN_SET", b["blockId"])
    add("LOCATION", "L02", "BOOKED_AS", "BOOKING", "R-2031", {"start": "16:30", "end": "18:30"})
    add("LOCATION", "L01", "GOVERNED_BY", "REGULATION", "permit-hangang")
    add("LOCATION", "L03", "GOVERNED_BY", "REGULATION", "zone-paju")
    for link in STATE.links:
        add(link["fromType"], link["fromId"], link["relation"], link["toType"], link["toId"], link.get("attrs"))
    return e


def label(t, i):
    n = node(t, i)
    return {"type": t, "id": i, "label": n["label"] if n else i}


async def ontology_entity(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    t, i = request.path_params["entity_type"], request.path_params["entity_id"]
    n = node(t, i)
    if not n:
        same = [x["id"] for x in (node(t, k) for k in _ids_of(t)) if x] if t in ENTITY_TYPES else []
        return error(404, "ENTITY_NOT_FOUND", f"{t} {i}를 찾을 수 없다", {"available": same[:10], "entityTypes": list(ENTITY_TYPES)})
    rels = []
    for ed in edges():
        if ed["from"] == (t, i):
            rels.append({"relation": ed["relation"], "direction": "out", "target": label(*ed["to"]), "attrs": ed["attrs"]})
        elif ed["to"] == (t, i):
            rels.append({"relation": ed["relation"], "direction": "in", "target": label(*ed["from"]), "attrs": ed["attrs"]})
    return JSONResponse({"entity": n, "relations": rels})


def _ids_of(t: str) -> list[str]:
    return {"ACTOR": list(fx.ACTORS), "SCENE": list(fx.SCENES), "BLOCK": [b["blockId"] for b in STATE.blocks],
            "LOCATION": list(fx.LOCATIONS), "EQUIPMENT": list(fx.EQUIPMENT), "CONTRACT": list(fx.CONTRACTS),
            "BOOKING": ["R-2031"], "PLAN_SET": list(fx.PLAN_SETS), "REGULATION": ["law-labor", "permit-hangang", "zone-paju", "guide-contract"],
            "PERSON": [str(k) for k in fx.USERS]}.get(t, [])


async def ontology_impact(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    b = await body(request)
    et, t, i = b.get("eventType"), b.get("entityType"), b.get("entityId")
    if et not in EVENT_TYPES:
        return error(400, "VALIDATION_ERROR", f"eventType은 {', '.join(EVENT_TYPES)} 중 하나", {"fields": ["eventType"]})
    if not node(t or "", i or ""):
        return error(404, "ENTITY_NOT_FOUND", f"{t} {i}를 찾을 수 없다", {"available": _ids_of(t or "")[:10]})
    w0, w1 = b.get("start") or "00:00", b.get("end") or "23:59"
    hit = []
    for blk in STATE.blocks:
        in_window = eng.overlap(blk["start"], blk["end"], w0, w1)
        if et == "WEATHER" and t == "LOCATION" and blk["locationId"] == i and fx.LOCATIONS[i]["outdoor"] and in_window:
            hit.append(blk)
        elif et == "ACTOR_SCHEDULE" and t == "ACTOR" and i in actor_ids_of(blk) and in_window:
            hit.append(blk)
        elif et == "LOCATION_CANCELLED" and t == "LOCATION" and blk["locationId"] == i:
            hit.append(blk)
        elif et == "EQUIPMENT_FAILURE" and t == "EQUIPMENT" and i in blk["equipmentIds"]:
            hit.append(blk)
    actors = sorted({a for blk in hit for a in actor_ids_of(blk)})
    locs = sorted({blk["locationId"] for blk in hit})
    regs = ["law-labor"] + [fx.LOCATIONS[x]["permit"]["docId"] for x in locs if fx.LOCATIONS[x]["permit"]] + \
           [fx.LOCATIONS[x]["zoneDocId"] for x in locs if fx.LOCATIONS[x]["zoneDocId"]]
    return JSONResponse({
        "event": {"eventType": et, "entityType": t, "entityId": i, "date": b.get("date", fx.SHOOT_DATE), "start": b.get("start"), "end": b.get("end")},
        "blocks": [{"blockId": x["blockId"], "locationId": x["locationId"], "start": x["start"], "end": x["end"], "hasPlanSet": x["blockId"] in fx.PLAN_SETS} for x in hit],
        "scenes": [s for x in hit for s in x["sceneIds"]],
        "actors": [{"actorId": a, "name": fx.ACTORS[a]["name"], "currentContractDocId": fx.ACTORS[a]["contractDocId"],
                    "contractVersion": fx.CONTRACTS[fx.ACTORS[a]["contractDocId"]]["version"],
                    "managerUserIds": [u["id"] for u in fx.USERS.values() if a in u.get("managedActorIds", [])]} for a in actors],
        "locations": locs,
        "equipment": sorted({e for x in hit for e in x["equipmentIds"]}),
        "bookings": ["R-2031"] if "L02" in locs else [],
        "regulationDocIds": list(dict.fromkeys(regs)),
    })


async def ontology_link(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)):
        return e
    b = await body(request)
    for side in ("from", "to"):
        if not node(b.get(f"{side}Type", ""), b.get(f"{side}Id", "")):
            return error(404, "ENTITY_NOT_FOUND", f"{b.get(side + 'Type')} {b.get(side + 'Id')}를 찾을 수 없다", {"entityTypes": list(ENTITY_TYPES)})
    link = {k: b.get(k) for k in ("fromType", "fromId", "relation", "toType", "toId")} | {"attrs": b.get("attrs") or {}}
    STATE.links.append(link)
    return JSONResponse({"linkId": len(STATE.links), **link}, status_code=201)


# ---------------------------------------------------------------- 계획안


async def get_plan_set(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    bid = request.path_params["block_id"]
    if bid not in fx.PLAN_SETS:
        return error(404, "BLOCK_NOT_FOUND", f"{bid}에는 1/2/3안이 없다", {"available": list(fx.PLAN_SETS)})
    cur = next(b for b in STATE.blocks if b["blockId"] == bid)
    plans = {pid: {**p, "packageName": fx.PACKAGES[p["packageId"]]["name"], "locationName": fx.LOCATIONS[p["locationId"]]["name"],
                   "extraCost": fx.PACKAGES[p["packageId"]]["extraCost"]} for pid, p in fx.PLAN_SETS[bid]["plans"].items()}
    return JSONResponse({"blockId": bid, "date": fx.SHOOT_DATE, "dataVersion": STATE.data_version,
                         "current": {k: cur[k] for k in ("locationId", "start", "end", "sceneIds")} | {"packageId": cur.get("packageId")},
                         "plans": plans, "elements": list(eng.ELEMENTS)})


async def availability(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    q = request.query_params
    t, i = q.get("entityType"), q.get("entityId")
    src = {"ACTOR": fx.ACTORS, "LOCATION": fx.LOCATIONS, "EQUIPMENT": fx.EQUIPMENT}.get(t or "")
    if src is None:
        return error(400, "VALIDATION_ERROR", "entityType은 ACTOR, LOCATION, EQUIPMENT 중 하나", {"fields": ["entityType"]})
    if i not in src:
        return error(404, "ENTITY_NOT_FOUND", f"{t} {i}를 찾을 수 없다", {"available": list(src)})
    if t == "ACTOR":
        busy = [b for b in STATE.blocks if i in actor_ids_of(b)]
    elif t == "LOCATION":
        busy = [b for b in STATE.blocks if b["locationId"] == i]
    else:
        busy = [b for b in STATE.blocks if i in b["equipmentIds"]]
    return JSONResponse({"entityType": t, "entityId": i, "date": q.get("date", fx.SHOOT_DATE), "windows": windows(src[i]["available"]),
                         "busy": [{"blockId": b["blockId"], "start": b["start"], "end": b["end"]} for b in busy]})


def _bad_choice(choice: Any, bid: str) -> JSONResponse | None:
    plans = list(fx.PLAN_SETS[bid]["plans"])
    if not isinstance(choice, dict) or any(choice.get(el) not in plans for el in eng.ELEMENTS):
        return error(400, "VALIDATION_ERROR", f"choice는 location, equipment, time 각각 {', '.join(plans)} 중 하나", {"fields": ["choice"]})
    return None


def _bad_weights(w: Any) -> JSONResponse | None:
    try:
        eng._norm_weights(w)
    except (ValueError, TypeError) as ex:
        return error(400, "VALIDATION_ERROR", str(ex), {"fields": ["weights"]})
    return None


async def evaluate(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    b = await body(request)
    bid = b.get("blockId")
    if bid not in fx.PLAN_SETS:
        return error(404, "BLOCK_NOT_FOUND", f"{bid}에는 1/2/3안이 없다", {"available": list(fx.PLAN_SETS)})
    if (e := _bad_weights(b.get("weights"))):
        return e
    res = eng.evaluate(STATE.blocks, bid, STATE.data_version, b.get("weights"), b.get("extraConstraints"), int(b.get("top", 5)))
    for r in res["ranked"]:  # 순위 안의 후보는 바로 build 없이 validate·save 할 수 있게 저장
        STATE.candidates[r["planHash"]] = eng.build_candidate(STATE.blocks, bid, r["choice"], STATE.data_version, b.get("extraConstraints"))
    return JSONResponse({**res, "dataVersion": STATE.data_version, "weights": eng._norm_weights(b.get("weights"))})


async def build(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    b = await body(request)
    bid = b.get("blockId")
    if bid not in fx.PLAN_SETS:
        return error(404, "BLOCK_NOT_FOUND", f"{bid}에는 1/2/3안이 없다", {"available": list(fx.PLAN_SETS)})
    if (e := _bad_choice(b.get("choice"), bid)):
        return e
    cand = eng.build_candidate(STATE.blocks, bid, b["choice"], STATE.data_version, b.get("extraConstraints"))
    STATE.candidates[cand["planHash"]] = cand
    return JSONResponse(cand)


async def validate(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    b = await body(request)
    cand = STATE.candidates.get(b.get("planHash", ""))
    if not cand:
        return error(404, "CANDIDATE_NOT_FOUND", "planHash에 해당하는 후보가 없다. build_schedule로 먼저 만든다", {"fields": ["planHash"]})
    if cand["dataVersion"] != STATE.data_version:
        return error(409, "STALE_PLAN", "후보를 만든 뒤 원본 데이터가 바뀌었다. 다시 평가한다",
                     {"candidateDataVersion": cand["dataVersion"], "currentDataVersion": STATE.data_version})
    if (e := _bad_weights(b.get("weights"))):
        return e
    return JSONResponse(eng.validate(cand, b.get("weights")))


async def save_plan(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)):
        return e
    b = await body(request)
    cand = STATE.candidates.get(b.get("planHash", ""))
    if not cand:
        return error(404, "CANDIDATE_NOT_FOUND", "planHash에 해당하는 후보가 없다", {"fields": ["planHash"]})
    if cand["dataVersion"] != STATE.data_version:
        return error(409, "STALE_PLAN", "원본 데이터가 바뀌었다. 다시 평가한다", {"currentDataVersion": STATE.data_version})
    res = eng.validate(cand, b.get("weights"))
    if not res["valid"]:  # 검증 게이트: 위반안은 승인 단계로 못 넘어간다
        return error(422, "HARD_VIOLATION", "하드 제약 위반이 있어 승인 요청을 만들 수 없다", {"violations": res["violations"]})
    pid = next(STATE.plan_ids)
    approvers = [{**a, "status": "PENDING", "reason": None, "decidedAt": None} for a in eng.required_approvers(cand)]
    STATE.plans[pid] = {"planId": pid, "version": f"v{next(STATE.plan_versions)}", "planHash": cand["planHash"], "candidate": cand,
                        "reason": b.get("reason"), "validation": res, "approvals": approvers, "status": "PENDING_APPROVAL",
                        "dataVersion": cand["dataVersion"], "taskId": request.headers["X-Task-Id"]}
    return JSONResponse({"planId": pid, "version": STATE.plans[pid]["version"], "status": "PENDING_APPROVAL", "dataVersion": cand["dataVersion"],
                         "requiredApprovers": approvers, "bookingNeeded": cand["bookingNeeded"], "total": res["total"]}, status_code=201)


async def commit(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)):
        return e
    key, hit = cached(request)
    if hit:
        return JSONResponse(hit)
    pid = int(request.path_params["plan_id"])
    plan = STATE.plans.get(pid)
    if not plan:
        return error(404, "PLAN_NOT_FOUND", f"계획안 {pid}가 없다", {"available": list(STATE.plans)})
    b = await body(request)
    if plan["status"] == "STALE" or plan["dataVersion"] != STATE.data_version or b.get("dataVersion") != STATE.data_version:
        plan["status"] = "STALE"
        return error(409, "STALE_PLAN", "승인 대기 중 원본이 바뀌어 이 계획안은 오래됐다. 최신 데이터로 다시 평가한다",
                     {"planDataVersion": plan["dataVersion"], "currentDataVersion": STATE.data_version})
    if plan["status"] != "APPROVED":
        pending = [a["role"] for a in plan["approvals"] if a["status"] != "APPROVED"]
        return error(409, "APPROVAL_REQUIRED", "필수 승인자 전원의 승인이 없다", {"planStatus": plan["status"], "pendingRoles": pending})
    res = eng.validate(plan["candidate"])
    if not res["valid"]:
        return error(422, "HARD_VIOLATION", "확정 직전 재검증에서 위반이 나왔다", {"violations": res["violations"]})
    STATE.blocks = copy.deepcopy(plan["candidate"]["day"])
    STATE.schedule_version = int(plan["version"].lstrip("v"))   # 확정 계획 버전 = 승인된 변경안 번호
    STATE.data_version += 1
    plan["status"] = "COMMITTED"
    recipients = [u["id"] for u in fx.USERS.values() if u["role"] != "PRODUCER"]
    STATE.outbox.append({"type": "CALLSHEET_PUBLISH", "planId": pid, "scheduleVersion": STATE.schedule_version, "recipients": recipients})
    for p in STATE.plans.values():
        if p["status"] in ("PENDING_APPROVAL", "APPROVED"):
            p["status"] = "STALE"
    resp = {"planId": pid, "scheduleVersion": STATE.schedule_version, "dataVersion": STATE.data_version, "callsheetJobs": len(recipients)}
    if key:
        STATE.idempotency[key] = resp
    return JSONResponse(resp)


async def booking(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)):
        return e
    key, hit = cached(request)
    if hit:
        return JSONResponse(hit, status_code=202)
    b = await body(request)
    plan = STATE.plans.get(int(b.get("planId", 0) or 0))
    if not plan:
        return error(404, "PLAN_NOT_FOUND", f"계획안 {b.get('planId')}가 없다", {"available": list(STATE.plans)})
    if plan["status"] not in ("APPROVED", "COMMITTED"):
        pending = [a["role"] for a in plan["approvals"] if a["status"] != "APPROVED"]
        return error(409, "APPROVAL_REQUIRED", "승인 전에는 예약을 요청할 수 없다", {"planStatus": plan["status"], "pendingRoles": pending})
    lid = b.get("locationId")
    if lid not in fx.LOCATIONS and lid not in {p["placeId"] for p in fx.OURPLACE}:
        return error(404, "LOCATION_NOT_FOUND", f"장소 {lid}가 없다", {"available": list(fx.LOCATIONS) + [p["placeId"] for p in fx.OURPLACE]})
    if lid in fx.LOCATIONS and "bookingId" not in fx.LOCATIONS[lid]:
        return error(409, "BOOKING_NOT_NEEDED", f"{fx.LOCATIONS[lid]['name']}은 자체 시설이라 예약이 필요 없다", {"locationId": lid})
    bid = f"BK-{next(STATE.booking_ids):04d}"
    blk = plan["candidate"]["block"]
    STATE.bookings[bid] = {"bookingId": bid, "planId": plan["planId"], "locationId": lid, "start": blk["start"], "end": blk["end"],
                           "status": "MANUAL_PENDING", "assigneeRole": "PRODUCTION_MANAGER",
                           "note": "아워플레이스 예약 API 협의 전: 제작실장이 직접 예약한 뒤 완료 처리한다"}
    if key:
        STATE.idempotency[key] = STATE.bookings[bid]
    return JSONResponse(STATE.bookings[bid], status_code=202)


# ---------------------------------------------------------------- 외부 서비스 (mock)


async def ext_weather(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    lid, date = request.query_params.get("locationId"), request.query_params.get("date", fx.SHOOT_DATE)
    if lid not in fx.LOCATIONS:
        return error(404, "LOCATION_NOT_FOUND", f"장소 {lid}가 없다", {"available": list(fx.LOCATIONS)})
    hourly = fx.WEATHER_HOURLY.get((lid, date), {})
    return JSONResponse({"locationId": lid, "date": date, "outdoor": fx.LOCATIONS[lid]["outdoor"], "source": "기상청 단기예보 (mock)",
                         "hourly": [{"hour": f"{h:02d}:00", "rainProb": p} for h, p in sorted(hourly.items())],
                         "rainThreshold": fx.RAIN_THRESHOLD})


async def ext_locations(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    q = request.query_params
    out = fx.OURPLACE
    if q.get("area"):
        out = [p for p in out if q["area"] in p["area"]]
    if q.get("indoor") in ("true", "false"):
        out = [p for p in out if p["indoor"] == (q["indoor"] == "true")]
    if q.get("minArea"):
        out = [p for p in out if p["areaPyeong"] >= int(q["minArea"])]
    if q.get("keyword"):
        kw = q["keyword"]
        out = [p for p in out if kw in p["name"] or (kw == "자연광" and p["naturalLight"])]
    return JSONResponse({"source": "아워플레이스 (mock, 공개 예약 API 미확인)", "results": out})


async def ext_route(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    a, b = request.query_params.get("from"), request.query_params.get("to")
    if a not in fx.LOCATIONS or b not in fx.LOCATIONS:
        return error(404, "LOCATION_NOT_FOUND", "출발 또는 도착 장소가 없다", {"available": list(fx.LOCATIONS)})
    km, mins = eng.route(a, b)
    return JSONResponse({"from": a, "to": b, "km": km, "minutes": mins, "source": "지도 경로 API (mock)"})


async def ext_quote(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    pid = request.query_params.get("packageId")
    if pid not in fx.PACKAGES:
        return error(404, "PACKAGE_NOT_FOUND", f"장비 묶음 {pid}가 없다", {"available": list(fx.PACKAGES)})
    p = fx.PACKAGES[pid]
    return JSONResponse({"packageId": pid, "name": p["name"], "date": request.query_params.get("date", fx.SHOOT_DATE),
                         "items": [{"equipmentId": e, "name": fx.EQUIPMENT[e]["name"], "available": windows(fx.EQUIPMENT[e]["available"])} for e in p["equipmentIds"]],
                         "extraCost": p["extraCost"], "source": "장비 렌탈사 견적 (mock)"})


# ---------------------------------------------------------------- 작업 이벤트


async def task_event(request: Request) -> JSONResponse:
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        return error(401, "UNAUTHORIZED", "X-Internal-Token이 없거나 틀렸다")
    STATE.events.append({"taskId": request.path_params["task_id"], **(await body(request))})
    return JSONResponse({"seq": len(STATE.events)}, status_code=202)


# ---------------------------------------------------------------- mock 전용 (실제 backend에는 없다)


async def mock_decision(request: Request) -> JSONResponse:
    """승인자 한 명의 승인·거절 흉내. 실제로는 화면 → backend /api/plans/{id}/approvals."""
    plan = STATE.plans.get(int(request.path_params["plan_id"]))
    if not plan:
        return error(404, "PLAN_NOT_FOUND", "계획안이 없다")
    b = await body(request)
    roles = [b["role"]] if b.get("role") else [a["role"] for a in plan["approvals"]]
    for a in plan["approvals"]:
        if a["role"] in roles:
            a["status"], a["reason"], a["decidedAt"] = ("APPROVED" if b.get("decision", "APPROVE") == "APPROVE" else "REJECTED"), b.get("reason"), "2026-11-12T10:47:00+09:00"
    if plan["status"] == "PENDING_APPROVAL":
        if any(a["status"] == "REJECTED" for a in plan["approvals"]):
            plan["status"] = "REJECTED"
        elif all(a["status"] == "APPROVED" for a in plan["approvals"]):
            plan["status"] = "APPROVED"
    rejections = [{"role": a["role"], "reason": a["reason"]} for a in plan["approvals"] if a["status"] == "REJECTED"]
    resume = None
    if plan["status"] in ("APPROVED", "REJECTED"):
        resume = {"type": "RESUME", "taskId": plan["taskId"], "planId": plan["planId"],
                  "approval": {"result": "ALL_APPROVED" if plan["status"] == "APPROVED" else "REJECTED", "rejections": rejections}}
    return JSONResponse({"planId": plan["planId"], "planStatus": plan["status"], "approvals": plan["approvals"], "resumeMessage": resume})


async def mock_bump(_: Request) -> JSONResponse:
    STATE.data_version += 1
    for p in STATE.plans.values():
        if p["status"] in ("PENDING_APPROVAL", "APPROVED"):
            p["status"] = "STALE"
    return JSONResponse({"dataVersion": STATE.data_version})


async def mock_state(_: Request) -> JSONResponse:
    return JSONResponse({"scheduleVersion": STATE.schedule_version, "dataVersion": STATE.data_version,
                         "blocks": STATE.blocks, "plans": {k: {x: v[x] for x in ("version", "status", "approvals")} for k, v in STATE.plans.items()},
                         "bookings": STATE.bookings, "outbox": STATE.outbox, "links": STATE.links, "events": STATE.events[-20:]})


async def mock_reset(_: Request) -> JSONResponse:
    STATE.reset()
    return JSONResponse({"reset": True})


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mock-backend", "contract": "1.0.0-rc2"})


app = Starlette(routes=[
    Route("/health", health),
    Route("/internal/ontology/entities/{entity_type}/{entity_id}", ontology_entity),
    Route("/internal/ontology/impact", ontology_impact, methods=["POST"]),
    Route("/internal/ontology/links", ontology_link, methods=["POST"]),
    Route("/internal/plan-sets/{block_id}", get_plan_set),
    Route("/internal/availability", availability),
    Route("/internal/plans/evaluate", evaluate, methods=["POST"]),
    Route("/internal/plans/build", build, methods=["POST"]),
    Route("/internal/plans/validate", validate, methods=["POST"]),
    Route("/internal/plans", save_plan, methods=["POST"]),
    Route("/internal/plans/{plan_id}/commit", commit, methods=["POST"]),
    Route("/internal/bookings", booking, methods=["POST"]),
    Route("/internal/external/weather", ext_weather),
    Route("/internal/external/locations", ext_locations),
    Route("/internal/external/route", ext_route),
    Route("/internal/external/equipment-quote", ext_quote),
    Route("/internal/tasks/{task_id}/events", task_event, methods=["POST"]),
    Route("/mock/plans/{plan_id}/decisions", mock_decision, methods=["POST"]),
    Route("/mock/data-version/bump", mock_bump, methods=["POST"]),
    Route("/mock/state", mock_state),
    Route("/mock/reset", mock_reset, methods=["POST"]),
])
