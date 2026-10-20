"""제약·점수 엔진 참조 구현 (아키텍처 v2 4장, 계약 rc2 contracts/ENGINE.md).

실제 엔진은 C가 Spring Boot 모듈로 만든다. 이 파일은 같은 규칙을 Python으로 옮긴 '정답지'다.
- 입력과 출력 형식은 contracts/schemas/plan.schema.json과 같다.
- C는 Java로 옮긴 뒤 같은 입력에 같은 결과가 나오는지 contracts/examples로 맞춰 본다.

용어
- 블록: 같은 장소에서 이어 찍는 씬 묶음. 재계획은 블록 하나(예: B2)를 다시 배치한다.
- 1/2/3안: 블록마다 제작사가 미리 만든 대안. 요소는 장소(location), 장비(equipment), 시간대(time).
- 선택(choice): 요소마다 어느 안에서 가져올지. {"location": "P2", "equipment": "P1", "time": "P2"}
"""
from __future__ import annotations

import hashlib
import itertools
import json
from typing import Any

from . import fixtures as fx

ELEMENTS = ("location", "equipment", "time")
CATEGORIES = ("CONTRACT", "SCHEDULE", "LAW", "BUDGET_LIMIT", "NO_FILMING_ZONE")


# ---------------------------------------------------------------- 시간·거리


def m(t: str) -> int:
    h, mm = t.split(":")
    return int(h) * 60 + int(mm)


def hm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def route(a: str, b: str) -> tuple[int, int]:
    """(km, 분). 같은 장소면 0."""
    return (0, 0) if a == b else fx.ROUTES[frozenset({a, b})]


def inside(start: str, end: str, windows) -> bool:
    return any(m(ws) <= m(start) and m(end) <= m(we) for ws, we in windows)


def overlap(a0: str, a1: str, b0: str, b1: str) -> bool:
    return m(a0) < m(b1) and m(b0) < m(a1)


# ---------------------------------------------------------------- 후보 만들기 (스케줄러)


def plan_set(block_id: str) -> dict:
    return fx.PLAN_SETS[block_id]


def build_candidate(base_blocks: list[dict], block_id: str, choice: dict, data_version: int, extra: list[dict] | None = None) -> dict:
    """선택한 요소로 블록을 다시 놓고 하루 계획 전체를 만든다. 판정은 하지 않는다."""
    plans = plan_set(block_id)["plans"]
    for el in ELEMENTS:
        if choice.get(el) not in plans:
            raise KeyError(f"{el}={choice.get(el)}")
    loc = plans[choice["location"]]["locationId"]
    pkg = plans[choice["equipment"]]["packageId"]
    start, end = plans[choice["time"]]["start"], plans[choice["time"]]["end"]
    old = next(b for b in base_blocks if b["blockId"] == block_id)
    new = {**old, "locationId": loc, "packageId": pkg, "equipmentIds": list(fx.PACKAGES[pkg]["equipmentIds"]), "start": start, "end": end}
    day = sorted([b for b in base_blocks if b["blockId"] != block_id] + [new], key=lambda b: m(b["start"]))
    km = sum(route(a["locationId"], b["locationId"])[0] for a, b in zip(day, day[1:]))
    base_km = sum(route(a["locationId"], b["locationId"])[0] for a, b in zip(base_blocks, base_blocks[1:]))
    extra = extra or []
    key = json.dumps({"b": block_id, "c": choice, "x": extra, "v": data_version}, sort_keys=True, ensure_ascii=False)
    changes = []
    if old["locationId"] != loc:
        changes.append({"element": "location", "from": old["locationId"], "to": loc})
    if (old["start"], old["end"]) != (start, end):
        changes.append({"element": "time", "from": f"{old['start']}-{old['end']}", "to": f"{start}-{end}"})
    if old.get("packageId") != pkg:
        changes.append({"element": "equipment", "from": old.get("packageId"), "to": pkg})
    if km != base_km:
        changes.append({"element": "route", "from": f"{base_km}km", "to": f"{km}km"})
    return {
        "planHash": hashlib.sha1(key.encode()).hexdigest()[:12],
        "dataVersion": data_version,
        "blockId": block_id,
        "choice": dict(choice),
        "block": new,
        "day": day,
        "extraCost": fx.PACKAGES[pkg]["extraCost"],
        "totalKm": km,
        "changes": changes,
        "bookingNeeded": loc != old["locationId"] and "bookingId" in fx.LOCATIONS[loc],
        "extraConstraints": extra,
    }


# ---------------------------------------------------------------- HARD 검증 (5분류)


def _v(category: str, code: str, target: dict, detail: str, hint: str, source: dict | None = None) -> dict:
    return {"category": category, "code": f"{category}.{code}", "target": target, "detail": detail, "source": source, "hint": hint}


def _actor_work(day: list[dict], actor_id: str) -> tuple[int, list[tuple[int, int]]]:
    """(오늘 일한 분, 연속 근무 구간들). 다른 장소로 이동하는 시간도 근무로 본다."""
    mine = [b for b in day if any(actor_id in fx.SCENES[s]["actorIds"] for s in b["sceneIds"])]
    if not mine:
        return 0, []
    work, segs = 0, []
    seg_start, seg_end = m(mine[0]["start"]), m(mine[0]["end"])
    work += seg_end - seg_start
    for prev, cur in zip(mine, mine[1:]):
        travel = route(prev["locationId"], cur["locationId"])[1]
        work += travel + m(cur["end"]) - m(cur["start"])
        rest = m(cur["start"]) - m(prev["end"]) - travel
        if rest < 30:          # 30분 미만 쉬면 이어서 일한 것으로 본다
            seg_end = m(cur["end"])
        else:
            segs.append((seg_start, seg_end))
            seg_start, seg_end = m(cur["start"]), m(cur["end"])
    segs.append((seg_start, seg_end))
    return work, segs


def check_hard(cand: dict) -> list[dict]:
    day, blk = cand["day"], cand["block"]
    loc = fx.LOCATIONS[blk["locationId"]]
    out: list[dict] = []
    actors = sorted({a for s in blk["sceneIds"] for a in fx.SCENES[s]["actorIds"]})

    # SCHEDULE: 배우 가능 시간, 장소 이용 시간, 장비 대여 시간, 겹침, 이동, 우천, 승인자 조건
    for a in actors:
        if not inside(blk["start"], blk["end"], fx.ACTORS[a]["available"]):
            w = ", ".join(f"{s}~{e}" for s, e in fx.ACTORS[a]["available"])
            out.append(_v("SCHEDULE", "ACTOR_AVAILABILITY", {"actorId": a, "blockId": blk["blockId"]},
                          f"{fx.ACTORS[a]['name']} 가능 시간 {w} 밖 ({blk['start']}~{blk['end']})",
                          f"가능 시간 {w} 안의 시간대를 고른다", {"docId": fx.ACTORS[a]["contractDocId"], "section": "4.1"}))
    if not inside(blk["start"], blk["end"], loc["available"]):
        w = ", ".join(f"{s}~{e}" for s, e in loc["available"])
        out.append(_v("SCHEDULE", "LOCATION_HOURS", {"locationId": loc["locationId"]},
                      f"{loc['name']} 이용 가능 시간 {w} 밖 ({blk['start']}~{blk['end']})", f"{w} 안의 시간대를 고른다"))
    for e in blk["equipmentIds"]:
        if not inside(blk["start"], blk["end"], fx.EQUIPMENT[e]["available"]):
            w = ", ".join(f"{s}~{t}" for s, t in fx.EQUIPMENT[e]["available"])
            out.append(_v("SCHEDULE", "EQUIPMENT_AVAILABILITY", {"equipmentId": e},
                          f"{fx.EQUIPMENT[e]['name']} 대여 가능 시간 {w} 밖", "다른 장비 묶음이나 시간대를 고른다"))
    for other in day:
        if other["blockId"] == blk["blockId"] or not overlap(blk["start"], blk["end"], other["start"], other["end"]):
            continue
        if other["locationId"] == blk["locationId"]:
            out.append(_v("SCHEDULE", "OVERLAP", {"blockId": other["blockId"], "locationId": blk["locationId"]},
                          f"같은 장소에서 {other['blockId']}({other['start']}~{other['end']})와 시간이 겹친다", "겹치지 않는 시간대를 고른다"))
        shared = sorted({a for s in other["sceneIds"] for a in fx.SCENES[s]["actorIds"]} & set(actors))
        if shared:
            out.append(_v("SCHEDULE", "OVERLAP", {"blockId": other["blockId"], "actorIds": shared},
                          f"배우 {', '.join(shared)}가 {other['blockId']}와 같은 시간에 배정된다", "겹치지 않는 시간대를 고른다"))
    for prev, cur in zip(day, day[1:]):
        km, mins = route(prev["locationId"], cur["locationId"])
        gap = m(cur["start"]) - m(prev["end"])
        if 0 <= gap < mins and blk["blockId"] in (prev["blockId"], cur["blockId"]):
            out.append(_v("SCHEDULE", "TRAVEL", {"from": prev["blockId"], "to": cur["blockId"]},
                          f"{prev['blockId']}→{cur['blockId']} 이동 {mins}분({km}km) 필요, 간격 {gap}분", "이동 시간이 충분한 시간대를 고른다"))
    if loc["outdoor"]:
        hourly = fx.WEATHER_HOURLY.get((loc["locationId"], fx.SHOOT_DATE), {})
        hours = range(m(blk["start"]) // 60, (m(blk["end"]) - 1) // 60 + 1)
        worst = max((hourly.get(h, 0) for h in hours), default=0)
        if worst >= fx.RAIN_THRESHOLD:
            out.append(_v("SCHEDULE", "OUTDOOR_RAIN", {"locationId": loc["locationId"], "start": blk["start"], "end": blk["end"]},
                          f"{loc['name']} {blk['start']}~{blk['end']} 강수 확률 최대 {worst}% (기준 {fx.RAIN_THRESHOLD}%)",
                          "실내 장소를 고르거나 비가 오기 전 시간대를 고른다", {"docId": "permit-hangang", "section": "3.1"}))
    for x in cand.get("extraConstraints") or []:
        kind = x.get("kind")
        hit = (kind == "EXCLUDE_LOCATION" and blk["locationId"] == x.get("locationId")) or \
              (kind == "EXCLUDE_PACKAGE" and blk.get("packageId") == x.get("packageId")) or \
              (kind == "EXCLUDE_TIME_WINDOW" and overlap(blk["start"], blk["end"], x["start"], x["end"])
               and x.get("locationId") in (None, blk["locationId"]))
        if hit:
            out.append(_v("SCHEDULE", "APPROVER_CONDITION", {"kind": kind, "fromRole": x.get("fromRole")},
                          f"{fx.ROLES.get(x.get('fromRole'), '승인자')} 조건 위반: {x.get('reason', '')}", "이 조건을 피하는 요소를 고른다"))
        if kind == "MAX_EXTRA_COST" and cand["extraCost"] > x["amount"]:
            out.append(_v("BUDGET_LIMIT", "APPROVER_CONDITION", {"amount": x["amount"]},
                          f"추가 비용 {cand['extraCost']:,}원 > 승인자 상한 {x['amount']:,}원", "추가 비용이 적은 장비·장소를 고른다"))

    # CONTRACT: 출연 계약 (야간 금지, 1일 최대 시간)
    for a in actors:
        c = fx.CONTRACTS[fx.ACTORS[a]["contractDocId"]]
        if c["nightBanAfter"] and m(blk["end"]) > m(c["nightBanAfter"]):
            out.append(_v("CONTRACT", "NIGHT_BAN", {"actorId": a}, f"{fx.ACTORS[a]['name']} {c['nightBanAfter']} 이후 촬영 불가 (계약 v{c['version']})",
                          f"{c['nightBanAfter']} 전에 끝나는 시간대를 고른다", {"docId": c["docId"], "section": "5.4"}))
        work, _ = _actor_work(day, a)
        if work > c["dailyMaxHours"] * 60:
            out.append(_v("CONTRACT", "DAILY_MAX", {"actorId": a}, f"{fx.ACTORS[a]['name']} 오늘 {work / 60:.1f}시간, 계약 한도 {c['dailyMaxHours']}시간",
                          "이동이 적은 장소나 짧은 일정을 고른다", {"docId": c["docId"], "section": "5.2"}))

    # LAW: 주 52시간, 휴게시간, 촬영 허가
    for a in actors:
        work, segs = _actor_work(day, a)
        week = fx.ACTORS[a]["weeklyHoursSoFar"] + work / 60
        if week > fx.WEEKLY_LIMIT_HOURS:
            out.append(_v("LAW", "WEEKLY_52H", {"actorId": a}, f"{fx.ACTORS[a]['name']} 이번 주 {week:.1f}시간 (한도 52시간)",
                          "오늘 근무를 줄이는 안을 고른다", {"docId": "law-labor", "section": "53"}))
        for s0, s1 in segs:
            if s1 - s0 > 240:
                out.append(_v("LAW", "BREAK", {"actorId": a, "start": hm(s0), "end": hm(s1)},
                              f"{fx.ACTORS[a]['name']} {hm(s0)}~{hm(s1)} 휴게 없이 {(s1 - s0) / 60:.1f}시간 연속",
                              "앞뒤 블록과 30분 이상 쉬는 시간이 생기는 시간대를 고른다", {"docId": "law-labor", "section": "54"}))
                break
    p = loc.get("permit")
    if loc["outdoor"] and (not p or p["status"] != "APPROVED" or not inside(blk["start"], blk["end"], [(p["start"], p["end"])])):
        out.append(_v("LAW", "PERMIT", {"locationId": loc["locationId"]}, f"{loc['name']} 촬영 허가 시간 밖이거나 허가 없음",
                      "허가 시간 안으로 옮긴다", {"docId": p["docId"], "section": p["section"]} if p else None))

    # BUDGET_LIMIT
    if cand["extraCost"] > fx.EPISODE_BUDGET_REMAINING:
        out.append(_v("BUDGET_LIMIT", "EPISODE", {"extraCost": cand["extraCost"]},
                      f"추가 비용 {cand['extraCost']:,}원 > 회차 남은 예산 {fx.EPISODE_BUDGET_REMAINING:,}원", "추가 비용이 적은 안을 고른다"))

    # NO_FILMING_ZONE: 드론 금지 구역 등
    if loc["droneProhibited"] and any(fx.EQUIPMENT[e].get("isDrone") for e in blk["equipmentIds"]):
        out.append(_v("NO_FILMING_ZONE", "DRONE", {"locationId": loc["locationId"]}, f"{loc['name']}는 드론 비행 금지 구역",
                      "드론이 없는 장비 묶음을 고른다", {"docId": loc["zoneDocId"], "section": "2.1"}))
    return out


# ---------------------------------------------------------------- SOFT 점수 (6개 기준)


def _norm_weights(w: dict | None) -> dict:
    w = {**fx.DEFAULT_WEIGHTS, **(w or {})}
    if any(v < 0 for v in w.values()) or set(w) != set(fx.DEFAULT_WEIGHTS):
        raise ValueError("weights는 location, equipment, weather, budget, time, distance 6개, 0 이상이어야 한다")
    total = sum(w.values()) or 1.0
    return {k: round(v / total, 4) for k, v in w.items()}


def score(cand: dict, weights: dict | None = None) -> tuple[dict, dict, float]:
    day, blk = cand["day"], cand["block"]
    loc = fx.LOCATIONS[blk["locationId"]]
    intent = fx.SCENES[blk["sceneIds"][0]]["intent"]
    s: dict[str, float] = {}
    s["location"] = fx.LOCATION_FIT.get(intent, {}).get(loc["locationId"], 0.5)
    s["equipment"] = fx.EQUIPMENT_SCORE[(blk["packageId"], "outdoor" if loc["outdoor"] else "indoor")]
    if loc["outdoor"]:
        hourly = fx.WEATHER_HOURLY.get((loc["locationId"], fx.SHOOT_DATE), {})
        worst = max((hourly.get(h, 0) for h in range(m(blk["start"]) // 60, (m(blk["end"]) - 1) // 60 + 1)), default=0)
        s["weather"] = 1 - worst / 100
    else:
        s["weather"] = 1.0
    s["budget"] = max(0.0, 1 - cand["extraCost"] / fx.EPISODE_BUDGET_REMAINING)
    span_h = (m(day[-1]["end"]) - m(day[0]["start"])) / 60
    waiting = sum(max(0, m(b["start"]) - m(a["end"]) - route(a["locationId"], b["locationId"])[1]) for a, b in zip(day, day[1:]))
    s["time"] = max(0.0, 1 - 0.5 * max(0.0, span_h - 8) / 6 - 0.5 * waiting / 240)
    s["distance"] = max(0.0, 1 - cand["totalKm"] / 120)
    s = {k: round(v, 4) for k, v in s.items()}
    w = _norm_weights(weights)
    total = round(sum(w[k] * s[k] for k in s), 4)
    return s, w, total


def validate(cand: dict, weights: dict | None = None) -> dict:
    violations = check_hard(cand)
    scores, w, total = score(cand, weights)
    return {"planHash": cand["planHash"], "valid": not violations, "violations": violations, "scores": scores, "weights": w, "total": total}


# ---------------------------------------------------------------- 1/2/3안 재평가 + 요소 재조합


def evaluate(base_blocks: list[dict], block_id: str, data_version: int, weights: dict | None = None,
             extra: list[dict] | None = None, top: int = 5) -> dict:
    """요소 조합(최대 3×3×3=27)을 전부 만들어 HARD로 거르고 SOFT 총점으로 줄 세운다."""
    plans = list(plan_set(block_id)["plans"])
    feasible, infeasible = [], {}
    for loc, eq, tm in itertools.product(plans, plans, plans):
        choice = {"location": loc, "equipment": eq, "time": tm}
        cand = build_candidate(base_blocks, block_id, choice, data_version, extra)
        res = validate(cand, weights)
        if res["valid"]:
            feasible.append({"choice": choice, "planHash": cand["planHash"], "total": res["total"], "scores": res["scores"],
                             "extraCost": cand["extraCost"], "totalKm": cand["totalKm"],
                             "recombined": len(set(choice.values())) > 1})
        else:
            for code in {v["code"] for v in res["violations"]}:
                infeasible[code] = infeasible.get(code, 0) + 1
    feasible.sort(key=lambda r: (-r["total"], r["extraCost"], json.dumps(r["choice"], sort_keys=True)))
    whole = {p: next((r for r in feasible if set(r["choice"].values()) == {p}), None) for p in plans}
    return {
        "blockId": block_id,
        "evaluated": len(plans) ** 3,
        "feasibleCount": len(feasible),
        "ranked": feasible[:top],
        "originalPlans": {p: ({"feasible": True, "total": r["total"]} if r else {"feasible": False}) for p, r in whole.items()},
        "infeasibleByCode": dict(sorted(infeasible.items(), key=lambda kv: -kv[1])),
    }


# ---------------------------------------------------------------- 다중 승인: 필수 승인자 지정 (Notion 메모)


APPROVER_RULES = [
    ("location", ["DIRECTOR", "DOP", "GAFFER", "ART_DIRECTOR", "SOUND_LEAD", "PRODUCTION_MANAGER"], "장소 변경"),
    ("equipment", ["DOP", "GRIP_CHIEF"], "장비 변경"),
    ("time", ["AD1", "GAFFER", "COSTUME_MAKEUP"], "시간대·콜타임 변경"),
    ("route", ["AD2"], "동선·이동 변경"),
]


def required_approvers(cand: dict) -> list[dict]:
    changed = {c["element"] for c in cand["changes"]}
    scopes: dict[str, list[str]] = {}
    for element, roles, label in APPROVER_RULES:
        if element in changed:
            for r in roles:
                scopes.setdefault(r, []).append(label)
    if cand["extraCost"] > 0:
        scopes.setdefault("PRODUCTION_PD", []).append(f"추가 비용 {cand['extraCost']:,}원")
    scopes.setdefault("PRODUCTION_MANAGER", []).append("일정 확정")
    order = list(fx.ROLES)
    return [{"role": r, "roleName": fx.ROLES[r], "userId": fx.ROLE_USER[r], "scope": ", ".join(dict.fromkeys(s))}
            for r, s in sorted(scopes.items(), key=lambda kv: order.index(kv[0]))]
