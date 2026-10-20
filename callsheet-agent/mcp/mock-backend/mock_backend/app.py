"""mock backend: Spring Boot `/internal/**`를 흉내 내는 개발용 서버.

D(business-mcp)와 E(Agent)가 B·C의 구현을 기다리지 않고 개발·테스트하기 위해 쓴다.
경로, 헤더, 응답, 오류 형식은 아키텍처 문서 6장·7장과 같다. 실제 backend가 준비되면
BACKEND_URL만 바꾸면 된다.

제약 검증은 '흉내'다. 진짜 규칙과 기준값은 C의 제약 엔진이 정한다.

실행:  uvicorn mock_backend.app:app --port 8080
"""
from __future__ import annotations

import itertools
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import fixtures as fx

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "dev-internal-token")
CHANGE_ROLES = {"PD", "AD"}


# ---------------------------------------------------------------- 상태 (메모리)

class State:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.drafts: dict[int, dict] = {}
        self.draft_ids = itertools.count(1001)
        self.schedules: dict[int, list[dict]] = {fx.BASE_SCHEDULE_ID: [dict(s) for s in fx.BASE_SLOTS]}
        self.current_schedule_id = fx.BASE_SCHEDULE_ID
        self.schedule_ids = itertools.count(fx.BASE_SCHEDULE_ID + 1)
        self.permits = {k: dict(v) for k, v in fx.PERMITS.items()}
        self.approvals: dict[str, str] = {}      # taskId → APPROVE | REJECT
        self.idempotency: dict[str, Any] = {}    # Idempotency-Key → 응답
        self.deliveries: list[dict] = []
        self.events: list[dict] = []


STATE = State()


# ---------------------------------------------------------------- 공통 함수

def error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse({"code": code, "message": message, "details": details or {}}, status_code=status)


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return minutes(a_start) < minutes(b_end) and minutes(b_start) < minutes(a_end)


def dates_between(d_from: str, d_to: str) -> list[str]:
    from datetime import date, timedelta

    start, end = date.fromisoformat(d_from), date.fromisoformat(d_to)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def similar_ids(target: str, candidates: list[str]) -> list[str]:
    digits = "".join(c for c in target if c.isdigit())
    if digits:
        n = int(digits)
        ranked = sorted(candidates, key=lambda c: abs(int("".join(ch for ch in c if ch.isdigit()) or 0) - n))
        return ranked[:3]
    return candidates[:3]


def weather_of(location_id: str, date: str) -> dict:
    return {"date": date, **fx.WEATHER.get((location_id, date), fx.DEFAULT_WEATHER)}


def availability_of(actor_id: str, date: str) -> list[dict]:
    """근무 가능 시간(WORK_DAY)에서 불가 시간을 뺀 구간."""
    free = [(minutes(fx.WORK_DAY["start"]), minutes(fx.WORK_DAY["end"]))]
    for block in fx.ACTOR_UNAVAILABLE.get((actor_id, date), []):
        b0, b1 = minutes(block["start"]), minutes(block["end"])
        nxt = []
        for f0, f1 in free:
            if b1 <= f0 or b0 >= f1:
                nxt.append((f0, f1))
                continue
            if f0 < b0:
                nxt.append((f0, b0))
            if b1 < f1:
                nxt.append((b1, f1))
        free = nxt
    return [{"start": hhmm(a), "end": hhmm(b)} for a, b in free]


def check_auth(request: Request, *, change: bool = False) -> JSONResponse | None:
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        return error(401, "UNAUTHORIZED", "X-Internal-Token이 없거나 틀렸다")
    for h in ("X-User-Id", "X-User-Role", "X-Production-Id", "X-Task-Id"):
        if not request.headers.get(h):
            return error(400, "VALIDATION_ERROR", f"{h} 헤더가 없다", {"fields": [h]})
    if change and request.headers["X-User-Role"] not in CHANGE_ROLES:
        return error(403, "FORBIDDEN", "PD 또는 조감독만 스케줄을 바꿀 수 있다")
    return None


def require_approval(request: Request) -> JSONResponse | None:
    task_id = request.headers["X-Task-Id"]
    if STATE.approvals.get(task_id) != "APPROVE":
        return error(409, "APPROVAL_REQUIRED", f"작업 {task_id}에 감독 승인 기록이 없다", {"taskId": task_id})
    return None


def idempotent(request: Request) -> tuple[str | None, Any]:
    key = request.headers.get("Idempotency-Key")
    return key, (STATE.idempotency.get(key) if key else None)


# ---------------------------------------------------------------- 제약 검증 (흉내)

def validate_draft(draft: dict) -> dict:
    d_from, d_to = draft["dateFrom"], draft["dateTo"]
    base = STATE.schedules.get(draft.get("baseScheduleId"), STATE.schedules[STATE.current_schedule_id])
    outside = [s for s in base if not (d_from <= s["date"] <= d_to)]
    slots = draft["slots"]
    effective = outside + slots
    v: list[dict] = []

    for s in slots:
        scene = fx.SCENES[s["sceneId"]]
        loc = fx.LOCATIONS[s["locationId"]]
        # 야외 + 비
        w = weather_of(s["locationId"], s["date"])
        if loc["outdoor"] and w["rainProb"] >= fx.RAIN_THRESHOLD:
            dry = [d for d in dates_between(d_from, d_to) if weather_of(s["locationId"], d)["rainProb"] < fx.RAIN_THRESHOLD]
            v.append({
                "type": "OUTDOOR_RAIN", "severity": "hard",
                "target": {"sceneId": s["sceneId"], "date": s["date"]},
                "detail": f"{loc['name']} 강수 확률 {w['rainProb']}% (기준 {fx.RAIN_THRESHOLD}%)",
                "source": {"docId": "guide-production", "section": "3.1"},
                "hint": f"{s['sceneId']}를 강수 확률이 낮은 날({', '.join(dry) or '범위 밖'})로 옮기거나 실내 씬과 날짜를 바꾼다",
            })
        # 허가 시간대
        if loc["outdoor"]:
            p = STATE.permits.get((s["locationId"], s["date"]))
            if not p or p["status"] == "CANCELLED":
                v.append({
                    "type": "PERMIT_WINDOW", "severity": "hard",
                    "target": {"locationId": s["locationId"], "date": s["date"]},
                    "detail": f"{loc['name']} {s['date']} 촬영 허가가 없다",
                    "source": {"docId": "permit-seoul", "section": "2.1"},
                    "hint": "허가가 있는 날짜로 옮긴다",
                })
            elif minutes(s["start"]) < minutes(p["allowedStart"]) or minutes(s["end"]) > minutes(p["allowedEnd"]):
                v.append({
                    "type": "PERMIT_WINDOW", "severity": "hard",
                    "target": {"locationId": s["locationId"], "date": s["date"]},
                    "detail": f"허가 시간 {p['allowedStart']}~{p['allowedEnd']} 밖({s['start']}~{s['end']})",
                    "source": {"docId": "permit-seoul", "section": "2.3"},
                    "hint": f"{p['allowedStart']}~{p['allowedEnd']} 안으로 옮긴다",
                })
        # 배우 불가 시간
        for actor_id in scene["actorIds"]:
            for block in fx.ACTOR_UNAVAILABLE.get((actor_id, s["date"]), []):
                if overlap(s["start"], s["end"], block["start"], block["end"]):
                    v.append({
                        "type": "ACTOR_UNAVAILABLE", "severity": "hard",
                        "target": {"actorId": actor_id, "sceneId": s["sceneId"], "date": s["date"]},
                        "detail": f"{fx.ACTORS[actor_id]['name']} {block['start']}~{block['end']} 촬영 불가({block['reason']})",
                        "source": {"docId": fx.ACTORS[actor_id]["contractDocId"], "section": "4.1"},
                        "hint": f"가능 시간: {', '.join(a['start'] + '~' + a['end'] for a in availability_of(actor_id, s['date']))}",
                    })

    # 장비 중복, 배우 중복, 근로시간 (전체 유효 스케줄 기준)
    by_date: dict[str, list[dict]] = {}
    for s in effective:
        by_date.setdefault(s["date"], []).append(s)
    for date, day in by_date.items():
        for a, b in itertools.combinations(day, 2):
            if not overlap(a["start"], a["end"], b["start"], b["end"]):
                continue
            for eq in set(a.get("equipmentIds", [])) & set(b.get("equipmentIds", [])):
                v.append({
                    "type": "EQUIPMENT_CONFLICT", "severity": "hard",
                    "target": {"equipmentId": eq, "date": date, "sceneIds": [a["sceneId"], b["sceneId"]]},
                    "detail": f"{fx.EQUIPMENT[eq]}이(가) {a['sceneId']}, {b['sceneId']}에 동시에 배정됨",
                    "source": None,
                    "hint": "둘 중 한 씬의 시간을 겹치지 않게 옮긴다",
                })
            for actor_id in set(fx.SCENES[a["sceneId"]]["actorIds"]) & set(fx.SCENES[b["sceneId"]]["actorIds"]):
                v.append({
                    "type": "ACTOR_UNAVAILABLE", "severity": "hard",
                    "target": {"actorId": actor_id, "date": date, "sceneIds": [a["sceneId"], b["sceneId"]]},
                    "detail": f"{fx.ACTORS[actor_id]['name']}이(가) 같은 시간에 두 씬에 배정됨",
                    "source": None,
                    "hint": "둘 중 한 씬의 시간을 옮긴다",
                })
        for actor_id, actor in fx.ACTORS.items():
            mine = [s for s in day if actor_id in fx.SCENES[s["sceneId"]]["actorIds"]]
            if not mine:
                continue
            span = (max(minutes(s["end"]) for s in mine) - min(minutes(s["start"]) for s in mine)) / 60
            if span > actor["dailyMaxHours"]:
                v.append({
                    "type": "ACTOR_WORK_HOURS", "severity": "hard",
                    "target": {"actorId": actor_id, "date": date},
                    "detail": f"일일 근로시간 {span:.1f}시간, 한도 {actor['dailyMaxHours']}시간",
                    "source": {"docId": actor["contractDocId"], "section": "5.2"},
                    "hint": f"{', '.join(s['sceneId'] for s in mine)} 중 하나를 다른 날로 옮긴다",
                })

    # 빠진 씬 (기준 스케줄 범위 안에 있었는데 초안에 없음)
    in_range = {s["sceneId"] for s in base if d_from <= s["date"] <= d_to}
    missing = sorted(in_range - {s["sceneId"] for s in slots})
    for sid in missing:
        v.append({
            "type": "SCENE_MISSING", "severity": "hard",
            "target": {"sceneId": sid},
            "detail": f"{sid}가 초안에서 빠졌다",
            "source": None,
            "hint": f"{sid}를 범위 안 어느 날짜에든 다시 배치한다",
        })

    base_pos = {s["sceneId"]: (s["date"], s["start"], s["locationId"]) for s in base}
    changed = sum(1 for s in slots if base_pos.get(s["sceneId"]) != (s["date"], s["start"], s["locationId"])) + len(missing)
    if changed:
        v.append({
            "type": "SCENES_CHANGED", "severity": "soft",
            "target": {"count": changed}, "detail": f"기준 대비 {changed}개 씬 변경",
            "source": None, "hint": "꼭 필요한 씬만 옮긴다",
        })
    moves = sum(max(len({s["locationId"] for s in day}) - 1, 0) for day in by_date.values())
    soft_score = round(max(0.0, 1 - 0.05 * changed - 0.05 * moves), 2)
    hard = [x for x in v if x["severity"] == "hard"]
    return {"valid": not hard, "violations": v, "softScore": soft_score, "changedScenes": changed}


# ---------------------------------------------------------------- 라우트

async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mock-backend"})


async def get_schedules(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    d_from, d_to = request.query_params.get("from"), request.query_params.get("to")
    if not d_from or not d_to:
        return error(400, "VALIDATION_ERROR", "from, to가 필요하다", {"fields": ["from", "to"]})
    slots = STATE.schedules[STATE.current_schedule_id]
    out = []
    for d in dates_between(d_from, d_to):
        day = sorted((s for s in slots if s["date"] == d), key=lambda s: s["start"])
        out.append({"date": d, "slots": [{k: s[k] for k in ("sceneId", "locationId", "start", "end", "equipmentIds")} for s in day]})
    return JSONResponse(out)


async def get_scene(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    sid = request.path_params["scene_id"]
    if sid not in fx.SCENES:
        return error(404, "SCENE_NOT_FOUND", f"씬 {sid}를 찾을 수 없다", {"similar": similar_ids(sid, list(fx.SCENES))})
    return JSONResponse(fx.SCENES[sid])


async def get_scenes(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    loc = request.query_params.get("locationId")
    if loc and loc not in fx.LOCATIONS:
        return error(404, "LOCATION_NOT_FOUND", f"장소 {loc}를 찾을 수 없다", {"available": list(fx.LOCATIONS)})
    return JSONResponse([s for s in fx.SCENES.values() if not loc or s["locationId"] == loc])


async def get_availability(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    aid = request.path_params["actor_id"]
    if aid not in fx.ACTORS:
        return error(404, "ACTOR_NOT_FOUND", f"배우 {aid}를 찾을 수 없다", {"available": list(fx.ACTORS)})
    d_from, d_to = request.query_params["from"], request.query_params["to"]
    return JSONResponse([{"date": d, "available": availability_of(aid, d)} for d in dates_between(d_from, d_to)])


async def get_permit(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    loc, date = request.path_params["location_id"], request.query_params.get("date", "")
    p = STATE.permits.get((loc, date))
    if not p:
        have = sorted(d for (l, d) in STATE.permits if l == loc)
        return error(404, "PERMIT_NOT_FOUND", f"{loc}의 {date} 허가가 없다", {"available": have})
    return JSONResponse({"locationId": loc, "date": date, **p})


async def get_weather(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    return JSONResponse(weather_of(request.query_params["locationId"], request.query_params["date"]))


def _check_draft(draft: dict) -> JSONResponse | None:
    unknown = [s["sceneId"] for s in draft.get("slots", []) if s["sceneId"] not in fx.SCENES]
    if unknown:
        return error(404, "SCENE_NOT_FOUND", f"씬 {unknown[0]}를 찾을 수 없다", {"similar": similar_ids(unknown[0], list(fx.SCENES))})
    bad_loc = [s["locationId"] for s in draft.get("slots", []) if s["locationId"] not in fx.LOCATIONS]
    if bad_loc:
        return error(404, "LOCATION_NOT_FOUND", f"장소 {bad_loc[0]}를 찾을 수 없다", {"available": list(fx.LOCATIONS)})
    return None


async def validate(request: Request) -> JSONResponse:
    if (e := check_auth(request)):
        return e
    draft = await request.json()
    if (e := _check_draft(draft)):
        return e
    return JSONResponse(validate_draft(draft))


async def save_draft(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)):
        return e
    body = await request.json()
    if (e := _check_draft(body["draft"])):
        return e
    draft_id = next(STATE.draft_ids)
    STATE.drafts[draft_id] = {"draft": body["draft"], "reason": body.get("reason"), "taskId": request.headers["X-Task-Id"]}
    return JSONResponse({"draftId": draft_id}, status_code=201)


async def confirm_draft(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)) or (e := require_approval(request)):
        return e
    key, cached = idempotent(request)
    if cached:
        return JSONResponse(cached)
    draft_id = int(request.path_params["draft_id"])
    if draft_id not in STATE.drafts:
        return error(404, "DRAFT_NOT_FOUND", f"초안 {draft_id}가 없다", {"available": list(STATE.drafts)})
    draft = STATE.drafts[draft_id]["draft"]
    result = validate_draft(draft)
    if not result["valid"]:
        return error(422, "HARD_VIOLATION", "하드 제약 위반이 남아 있다",
                     {"violations": [x for x in result["violations"] if x["severity"] == "hard"]})
    base = STATE.schedules[STATE.current_schedule_id]
    new_slots = [s for s in base if not (draft["dateFrom"] <= s["date"] <= draft["dateTo"])] + draft["slots"]
    sid = next(STATE.schedule_ids)
    STATE.schedules[sid] = new_slots
    STATE.current_schedule_id = sid
    resp = {"scheduleId": sid}
    if key:
        STATE.idempotency[key] = resp
    return JSONResponse(resp)


async def patch_permit(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)) or (e := require_approval(request)):
        return e
    pid = int(request.path_params["permit_id"])
    status = (await request.json()).get("status")
    for p in STATE.permits.values():
        if p["permitId"] == pid:
            p["status"] = status
            return JSONResponse({"permitId": pid, "status": status})
    return error(404, "PERMIT_NOT_FOUND", f"허가 {pid}가 없다", {"available": [p["permitId"] for p in STATE.permits.values()]})


async def send_callsheets(request: Request) -> JSONResponse:
    if (e := check_auth(request, change=True)) or (e := require_approval(request)):
        return e
    key, cached = idempotent(request)
    if cached:
        return JSONResponse(cached)
    body = await request.json()
    unknown = [r for r in body["recipientIds"] if r not in fx.USERS]
    if unknown:
        return error(404, "RECIPIENT_NOT_FOUND", f"수신자 {unknown}가 없다", {"available": list(fx.USERS)})
    for r in body["recipientIds"]:
        STATE.deliveries.append({"scheduleId": body["scheduleId"], "recipientId": r, "status": "QUEUED"})
    resp = {"queued": len(body["recipientIds"]), "recipients": body["recipientIds"]}
    if key:
        STATE.idempotency[key] = resp
    return JSONResponse(resp, status_code=202)


async def task_event(request: Request) -> JSONResponse:
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        return error(401, "UNAUTHORIZED", "X-Internal-Token이 없거나 틀렸다")
    body = await request.json()
    STATE.events.append({"taskId": request.path_params["task_id"], **body})
    return JSONResponse({"seq": len(STATE.events)}, status_code=202)


# ---- mock 전용: 실제 backend에는 없다 (승인 흉내, 상태 확인, 초기화)

async def mock_approve(request: Request) -> JSONResponse:
    body = await request.json() if await request.body() else {}
    STATE.approvals[request.path_params["task_id"]] = body.get("decision", "APPROVE")
    return JSONResponse({"taskId": request.path_params["task_id"], "decision": STATE.approvals[request.path_params["task_id"]]})


async def mock_state(_: Request) -> JSONResponse:
    return JSONResponse({
        "currentScheduleId": STATE.current_schedule_id,
        "drafts": list(STATE.drafts),
        "approvals": STATE.approvals,
        "deliveries": STATE.deliveries,
        "events": STATE.events[-20:],
    })


async def mock_reset(_: Request) -> JSONResponse:
    STATE.reset()
    return JSONResponse({"reset": True})


app = Starlette(routes=[
    Route("/health", health),
    Route("/internal/schedules", get_schedules),
    Route("/internal/scenes/{scene_id}", get_scene),
    Route("/internal/scenes", get_scenes),
    Route("/internal/actors/{actor_id}/availability", get_availability),
    Route("/internal/locations/{location_id}/permits", get_permit),
    Route("/internal/weather", get_weather),
    Route("/internal/schedule/validate", validate, methods=["POST"]),
    Route("/internal/schedule-drafts", save_draft, methods=["POST"]),
    Route("/internal/schedule-drafts/{draft_id}/confirm", confirm_draft, methods=["POST"]),
    Route("/internal/permits/{permit_id}", patch_permit, methods=["PATCH"]),
    Route("/internal/callsheets/send", send_callsheets, methods=["POST"]),
    Route("/internal/tasks/{task_id}/events", task_event, methods=["POST"]),
    Route("/mock/tasks/{task_id}/approve", mock_approve, methods=["POST"]),
    Route("/mock/state", mock_state),
    Route("/mock/reset", mock_reset, methods=["POST"]),
])
