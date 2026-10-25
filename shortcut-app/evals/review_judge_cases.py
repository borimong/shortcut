"""자체 검토(self_review) 채점 평가에 쓰는 결함 주입 케이스를 만듭니다.

실제 실행에서 복원한 입력(review_judge_real.json)마다 사건, 후보, 직전 거절은 그대로 두고
승인자가 추가 질문 없이 승인할 수 있는 안(gold)을 새로 쓴 뒤, 결함을 하나씩 넣은 변형을 만듭니다.
정답은 구성에서 나옵니다. 결함 변형은 겨냥한 항목 점수가 gold보다 낮아야 하고,
expect_pass가 정해진 변형은 80점 통과 여부가 그 값과 같아야 합니다.
"""

# 케이스를 만드는 안쪽 함수는 루프 안에서 바로 호출되므로 루프 변수를 늦게 읽는 문제가 없다.
# ruff: noqa: B023

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REAL_PATH = Path(__file__).resolve().parent / "review_judge_real.json"
CATEGORIES = ["CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER"]
# 실제 실행에서 각 범주에 인용된 조항 중 범주에 맞는 것만 골랐다.
EVIDENCE = {
    "CONTRACT": ["contract-actor-a-v3#1", "contract-actor-b-v1#1"],
    "SCHEDULE": ["contract-actor-a-v3#4", "contract-actor-b-v1#2"],
    "LAW": ["law-labor-standards#1", "law-labor-standards#3"],
    "BUDGET": ["budget-approval-policy#1"],
    "NO_FLY_ZONE": ["no-fly-zone-notice#1"],
    "DISASTER": ["safety-disaster-weather#1"],
    "WEATHER": ["safety-disaster-weather#2"],
}
ISSUE_NAMES = {"LOCATION": "장소", "EQUIPMENT": "장비", "TIME": "시간"}
ROLE_NAMES = {"SOUND": "동시녹음팀장", "DOP": "촬영감독", "DIRECTOR": "연출감독", "AD1": "조감독", "PRODUCER": "제작 PD"}


@dataclass
class Case:
    id: str
    base: str
    variant: str
    state: dict[str, Any]
    # 점수가 gold보다 내려가야 하는 항목. 없으면 gold와 같아야 하는 변형이다.
    target: str | None = None
    # 80점 통과 여부의 정답. 판단이 갈릴 수 있는 변형은 None으로 두고 항목 점수만 본다.
    expect_pass: bool | None = None
    expect_actions: list[str] = field(default_factory=list)
    # 프롬프트에 적힌 상한 규칙. 예: 근거 0건 범주가 있으면 evidence 12점 이하
    caps: dict[str, int] = field(default_factory=dict)


def _won(value: int) -> str:
    return f"{value:,}원"


def _items(candidate: dict[str, Any]) -> str:
    return ", ".join(item["name"] for item in candidate["equipment"]["items"])


def _checklist(candidate: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = candidate["time"]["start"], candidate["time"]["end"]
    loc = candidate["location"]["name"]
    drone = any(item["name"] == "드론" for item in candidate["equipment"]["items"])
    notes = {
        "CONTRACT": f"배우 A, B 계약상 촬영 가능 시간 안({start}~{end}), 야간 조항 해당 없음",
        "SCHEDULE": f"배우 A 계약 제9조 일정 변경 통보는 승인 즉시 제작실장이 처리, {loc} 이용 시간과 세팅 1시간 확보",
        "LAW": f"당일 총 근로 {start}~{end} 촬영 포함 주 52시간 이내, 휴게 1시간 배정",
        "BUDGET": f"장소와 장비 비용 {_won(candidate['cost'])}, 블록 예산 상한 이내",
        "NO_FLY_ZONE": f"{loc} 반경 비행 금지 구역 아님" if drone else "드론 미사용으로 해당 없음",
        "DISASTER": f"{loc} 소재 지역에 {start}~{end} 발령된 긴급재난문자 없음",
        "WEATHER": "실내 장소라 시간당 강수량 기준 적용 대상 아님"
        if candidate["location"]["indoor"]
        else f"{loc} {start}~{end} 예보 강수량이 촬영 불가 기준 미만",
    }
    return [{"constraint": c, "status": "PASS", "note": notes[c], "evidenceIds": list(EVIDENCE[c])} for c in CATEGORIES]


def _rejection_sentence(rejection: dict[str, Any]) -> str:
    issues = ", ".join(ISSUE_NAMES.get(i, i) for i in rejection.get("issues") or []) or "지적된 요소"
    role = ROLE_NAMES.get(rejection.get("role"), rejection.get("role", "승인자"))
    return f"직전 안은 {role}이 '{rejection['reason']}' 사유로 거절해, 문제로 지목된 {issues}를 바꿨습니다."


def _explanation(
    candidate: dict[str, Any],
    state: dict[str, Any],
    *,
    with_rejection: bool = True,
    place_name: str | None = None,
    wrong_cost: bool = False,
) -> str:
    """place_name과 wrong_cost는 엔진이 확인한 사실과 다른 설명을 만들 때만 씁니다."""
    event = state["event"]
    loc = candidate["location"]
    feasible = [c for c in state["candidates"] if c["feasible"]]
    current_cost = candidate["cost"] - candidate["extraCost"]
    place = "실내" if loc["indoor"] else "야외"
    parts = []
    if with_rejection and state.get("last_rejection"):
        parts.append(_rejection_sentence(state["last_rejection"]))
    name = place_name or loc["name"]
    parts.append(
        f"'{event['detail']}' 때문에 {_current_place(state)} 촬영을 유지하기 어렵습니다. 새 장소는 {name}({place}, 목동 기준 {candidate['distanceKm']}km)입니다."
    )
    parts.append(
        f"장비는 {_items(candidate)}, 촬영은 {candidate['time']['start']}~{candidate['time']['end']}로 배우 A, B 계약 가용 시간 안입니다."
    )
    if wrong_cost or candidate["extraCost"] == 0:
        parts.append("장소와 장비 비용은 현재 확정안과 같아 추가 비용이 없습니다.")
    else:
        parts.append(
            f"장소와 장비 비용은 {_won(candidate['cost'])}으로 현재 확정안 {_won(current_cost)}보다 {_won(candidate['extraCost'])} 늘지만, "
            f"늘어난 몫은 {name} 대관료이며 블록 예산 상한 안입니다."
        )
    parts.append(
        f"남은 실행 가능 후보 {len(feasible)}개 중 종합 점수 {candidate['totalScore']}로 가장 높고, "
        + ("실내라 비 예보의 영향을 받지 않습니다." if loc["indoor"] else "예보 강수량이 촬영 불가 기준 미만입니다.")
    )
    return " ".join(parts)


def _current_place(state: dict[str, Any]) -> str:
    return ((state.get("plan_set") or {}).get("current") or {}).get("location", {}).get("name", "한강 공원")


def _unresolved(candidate: dict[str, Any]) -> list[str]:
    loc = candidate["location"]["name"]
    return [
        "제작실장: 배우 A, B 소속사에 일정 변경 통보, 승인 즉시(계약 제9조)",
        f"제작부: {loc} 대관 예약 확정, 승인 후 1시간 안",
        f"조감독: 스태프 {loc} 집결 시각과 이동 차량 공지, 오늘 18시까지",
    ]


def gold_state(record: dict[str, Any]) -> dict[str, Any]:
    src = record["state"]
    candidate = copy.deepcopy(src["selected_plan"]["candidate"])
    state = {
        "event": src["event"],
        "candidates": src["candidates"],
        "last_rejection": src.get("last_rejection"),
        "review_round": 0,
        "review_history": [],
        "best_review": None,
        "failed_hashes": [],
        "review_skipped": [],
        "info_retries": 0,
        "plan_set": src.get("plan_set") or {},
    }
    state["selected_plan"] = {
        "hash": candidate["hash"],
        "candidate": candidate,
        "explanation": _explanation(candidate, state),
        "checklist": _checklist(candidate, src["event"]),
        "unresolved": _unresolved(candidate),
    }
    return state


def _paraphrase(state: dict[str, Any]) -> None:
    plan = state["selected_plan"]
    sentences = [s.rstrip(".") for s in plan["explanation"].split(". ")]
    # 문장 순서를 바꾸고 말투만 다르게 한다. 사실과 숫자는 그대로다.
    text = ". ".join([*sentences[1:], sentences[0]]) + "."
    plan["explanation"] = text.replace("새 장소는", "변경 장소는").replace("늘지만", "증가하지만").replace("가장 높고", "1위이고")
    plan["checklist"] = list(reversed(plan["checklist"]))
    plan["unresolved"] = [u.replace(": ", " 담당, ").replace("승인 즉시", "승인 직후") for u in plan["unresolved"]]


def _drop_evidence(state: dict[str, Any], categories: list[str]) -> None:
    for item in state["selected_plan"]["checklist"]:
        if item["constraint"] in categories:
            item["evidenceIds"] = []
            item["note"] = item["note"] + " (근거 조항 미확인)"


def _vague_explanation(state: dict[str, Any]) -> None:
    state["selected_plan"]["explanation"] = "상황 변화에 맞춰 장소를 변경했습니다. 비용이 조금 늘 수 있지만 문제없는 수준입니다."


def _vague_unresolved(state: dict[str, Any]) -> None:
    state["selected_plan"]["unresolved"] = ["소속사 통보", "예약 확정", "기타 확인 필요"]


def _bases(records: list[dict[str, Any]] | None) -> dict[tuple, dict]:
    records = records if records is not None else json.loads(REAL_PATH.read_text(encoding="utf-8"))
    # 사건, 선택 후보, 직전 거절 유무가 같은 입력은 하나로 본다. 가장 최근 기록을 쓴다.
    bases: dict[tuple, dict] = {}
    for record in records:
        src = record["state"]
        key = (src["event"]["detail"], src["selected_plan"]["hash"], bool(src.get("last_rejection")))
        bases[key] = record
    return bases


def build_cases(records: list[dict[str, Any]] | None = None) -> list[Case]:
    bases = _bases(records)
    cases: list[Case] = []
    for index, record in enumerate(bases.values()):
        base = f"b{index:02d}"
        gold = gold_state(record)
        candidate = gold["selected_plan"]["candidate"]
        # 틀린 장소는 거절된 장소와 겹치지 않게 골라, 설명 항목만 겨냥하게 한다.
        rejected_id = (gold.get("last_rejection") or {}).get("location_id")
        others = [
            c["location"]["name"]
            for c in gold["candidates"]
            if c["location"]["name"] not in (candidate["location"]["name"], _current_place(gold))
            and c["location"]["id"] != rejected_id
        ]
        wrong_place = others[0] if others else "파주 세트장"

        def variant(name: str, mutate=None, **meta) -> None:
            state = copy.deepcopy(gold)
            if mutate:
                mutate(state)
            cases.append(Case(f"{base}-{name}", base, name, state, **meta))

        variant("gold", expect_pass=True)
        variant("paraphrase", _paraphrase, expect_pass=True)

        def anchored(state: dict[str, Any]) -> None:
            # 앞 회차가 낮은 점수였고 지적한 점을 이번 안이 모두 고친 경우다. 점수가 gold만큼 올라가야 한다.
            entry = {
                "round": 1,
                "score": 62,
                "hash": candidate["hash"],
                "action": "REWRITE",
                "breakdown": {"evidence": 14, "rejection": 12, "optimization": 12, "explanation": 12, "risk": 12},
                "feedback": ["설명에 시간, 비용, 거리 숫자가 없습니다.", "미확정 항목에 담당과 기한이 없습니다."],
            }
            state.update(
                {
                    "review_round": 1,
                    "review_history": [entry],
                    "best_review": {"score": 62, "round": 1, "plan": state["selected_plan"]},
                }
            )

        variant("anchor_low", anchored, expect_pass=True)

        def warn_two(state: dict[str, Any]) -> None:
            for item in state["selected_plan"]["checklist"]:
                if item["constraint"] in ("SCHEDULE", "NO_FLY_ZONE"):
                    item["status"] = "WARN"
                    item["note"] = item["note"] + ", 조항 해석이 애매해 현장 확인 필요"

        variant("ev_warn2", warn_two, target="evidence")
        variant(
            "ev_missing1",
            lambda s: _drop_evidence(s, ["DISASTER"]),
            target="evidence",
            caps={"evidence": 12},
            expect_actions=["MORE_EVIDENCE"],
        )
        variant(
            "ev_missing3",
            lambda s: _drop_evidence(s, ["CONTRACT", "LAW", "NO_FLY_ZONE"]),
            target="evidence",
            caps={"evidence": 12},
            expect_pass=False,
            expect_actions=["MORE_EVIDENCE"],
        )
        variant("expl_vague", _vague_explanation, target="explanation", expect_pass=False, expect_actions=["REWRITE"])

        def wrong_fact(state: dict[str, Any]) -> None:
            # 엔진이 확인한 사실과 다른 장소 이름과 추가 비용을 적는다.
            state["selected_plan"]["explanation"] = _explanation(
                candidate, state, place_name=wrong_place, wrong_cost=candidate["extraCost"] > 0
            )

        variant("expl_wrong", wrong_fact, target="explanation", expect_pass=False, expect_actions=["REWRITE"])
        variant("risk_vague", _vague_unresolved, target="risk", expect_actions=["REWRITE"])
        if gold.get("last_rejection"):

            def ignore_rejection(state: dict[str, Any]) -> None:
                state["selected_plan"]["explanation"] = _explanation(candidate, state, with_rejection=False)

            variant("rej_ignored", ignore_rejection, target="rejection", expect_pass=False, expect_actions=["REWRITE"])

        def stacked(state: dict[str, Any]) -> None:
            _vague_explanation(state)
            _vague_unresolved(state)
            _drop_evidence(state, ["CONTRACT", "LAW", "NO_FLY_ZONE"])

        variant("stacked", stacked, target="explanation", caps={"evidence": 12}, expect_pass=False)
    return cases


def _gold2_explanation(candidate: dict[str, Any], state: dict[str, Any]) -> str:
    """gold와 다른 형식으로 쓴 흠 없는 설명입니다. 채점이 특정 문장 틀에 맞춰진 것은 아닌지 봅니다."""
    loc = candidate["location"]["name"]
    feasible = [c for c in state["candidates"] if c["feasible"]]
    lines = [f"{loc} 안으로 변경합니다. 사유는 {state['event']['detail']}입니다."]
    rejection = state.get("last_rejection")
    if rejection:
        issues = ", ".join(ISSUE_NAMES.get(i, i) for i in rejection.get("issues") or []) or "문제 요소"
        lines.append(f"지난 안에서 지적된 {rejection['reason']} 문제는 {issues}를 {loc} 쪽으로 바꿔 해소했습니다.")
    lines.append(
        f"바뀐 점은 장소({_current_place(state)}에서 {loc}), 장비({_items(candidate)}), "
        f"시간({candidate['time']['start']}~{candidate['time']['end']})입니다."
    )
    if candidate["extraCost"] > 0:
        lines.append(
            f"목동에서 {candidate['distanceKm']}km 거리이고, 비용은 {_won(candidate['cost'])}으로 현재보다 {_won(candidate['extraCost'])} "
            "많은데 이는 실내 대관료가 붙기 때문입니다."
        )
    else:
        lines.append(
            f"목동에서 {candidate['distanceKm']}km 거리이고, 비용은 {_won(candidate['cost'])}으로 현재보다 늘지 않습니다."
        )
    lines.append(f"실행 가능한 후보 {len(feasible)}개 가운데 엔진 점수 {candidate['totalScore']}로 1위입니다.")
    return " ".join(lines)


def build_holdout(records: list[dict[str, Any]] | None = None) -> list[Case]:
    """채점 코드를 고친 뒤 결과를 보기 전에 만든 별도 세트입니다. 결함 문장과 유형을 본 세트와 다르게 썼다."""
    cases: list[Case] = []
    for index, record in enumerate(_bases(records).values()):
        base = f"h{index:02d}"
        gold = gold_state(record)
        candidate = gold["selected_plan"]["candidate"]
        gold["selected_plan"]["explanation"] = _gold2_explanation(candidate, gold)
        loc = candidate["location"]["name"]
        gold["selected_plan"]["unresolved"] = [
            "소속사 일정 변경 통보 (담당 제작실장, 승인 직후)",
            f"{loc} 대관 예약 (담당 제작부, 오늘 15시 전)",
            "스태프 집결 공지 (담당 조감독, 오늘 18시까지)",
        ]

        def variant(name: str, mutate=None, **meta) -> None:
            state = copy.deepcopy(gold)
            if mutate:
                mutate(state)
            cases.append(Case(f"{base}-{name}", base, name, state, **meta))

        def set_text(text: str):
            return lambda s: s["selected_plan"].update(explanation=text)

        variant("gold", expect_pass=True)
        variant(
            "vague",
            set_text("기상 악화로 실내 촬영지로 바꿨고 일정은 큰 변동이 없습니다. 승인 부탁드립니다."),
            target="explanation",
            expect_pass=False,
        )
        text = gold["selected_plan"]["explanation"]
        wrong_km = text.replace(f"{candidate['distanceKm']}km", f"{candidate['distanceKm'] + 23}km")
        variant("wrong_distance", set_text(wrong_km), target="explanation", expect_pass=False)
        wrong_time = text.replace(candidate["time"]["start"], "15:30")
        variant("wrong_time", set_text(wrong_time), target="explanation", expect_pass=False)
        chosen = {item["name"] for item in candidate["equipment"]["items"]}
        foreign = sorted({i["name"] for c in gold["candidates"] for i in c["equipment"]["items"]} - chosen)
        if foreign:
            variant("wrong_equipment", set_text(text + f" {foreign[0]}도 함께 씁니다."), target="explanation", expect_pass=False)
        if gold.get("last_rejection"):
            vague_rej = _gold2_explanation(candidate, {**gold, "last_rejection": None}).replace(
                "입니다.", "입니다. 직전 의견도 반영했습니다.", 1
            )
            variant("rej_vague", set_text(vague_rej), target="rejection", expect_pass=False)
        variant(
            "risk_partial",
            lambda s: s["selected_plan"].update(
                unresolved=["소속사 통보 (제작실장)", "대관 예약 (제작부)", "집결 공지 (조감독)"]
            ),
            target="risk",
        )
        if candidate["extraCost"] > 0:
            no_reason = text.replace("많은데 이는 실내 대관료가 붙기 때문입니다.", "많습니다.")
            variant("cost_no_reason", set_text(no_reason), target="optimization")
        variant("ev_missing2", lambda s: _drop_evidence(s, ["SCHEDULE", "WEATHER"]), target="evidence", expect_pass=False)
    return cases


if __name__ == "__main__":
    built = build_cases()
    from collections import Counter

    print(len(built), Counter(c.variant for c in built))
    print(json.dumps(built[0].state["selected_plan"], ensure_ascii=False, indent=1))
