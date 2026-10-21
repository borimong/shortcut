"""평가 시나리오를 실제 API로 돌려 Harness 지표를 모으고, 두 실행 결과를 나란히 비교합니다.

사용법:
  python -m evals.run_eval --label before            # 시나리오 전체 실행 후 outputs/eval_before.json, .md 저장
  python -m evals.run_eval --label after --only rain_approve
  python -m evals.run_eval --compare before after    # outputs/eval_compare_before_after.md 저장
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.getenv("SHORTCUT_URL", "http://localhost:18080")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "change-me-internal-token")
PASSWORD = "shortcut1234"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
HARD = ("CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER")
ROLE_USERS = {"PRODUCER": "pd", "DIRECTOR": "director", "AD1": "ad1", "AD2": "ad2", "DOP": "dop", "SOUND": "sound"}
# 승인 대기까지 LLM 호출이 여러 번 이어지므로 120초 한도에 여유를 더해 기다린다.
WAIT_SECONDS = 180


@dataclass(frozen=True)
class Step:
    """한 번의 거절 뒤 다음 변경안이 지켜야 할 것. 요소는 LOCATION, TIME, EQUIPMENT이다."""

    changed: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()
    excluded_equipment_ids: tuple[int, ...] = ()
    # 다음 변경안의 필수 승인자에 들어 있어야 하는 역할
    approvers: tuple[str, ...] = ()


@dataclass
class Scenario:
    name: str
    event: dict[str, Any]
    # 루프마다 내릴 결정. ("REJECT", 역할, 사유, 문제 요소 목록) 또는 ("APPROVE",)
    decisions: list[tuple] = field(default_factory=lambda: [("APPROVE",)])
    disaster_alerts: list[dict[str, Any]] = field(default_factory=list)
    fixture: str | None = None
    expect_status: str = "DONE"
    expect_location_id: int | None = None
    # 최종 안의 장소가 몇 안에서 왔는지. 4면 1/2/3안 밖의 대체 장소다.
    expect_location_source: int | None = None
    # i번째 항목은 i번째 변경안에서 i+1번째 변경안으로 바뀔 때의 기대값이다. 키는 Step을 따른다.
    expect_steps: tuple[Step, ...] = ()
    expect_max_extra_cost: int | None = None
    expect_stop_condition: str | None = None
    # 권한 없는 접수, 중복 접수, 권한 없는 승인, 잘못된 거절 입력이 막히는지 함께 확인한다.
    check_guards: bool = False
    # 작업이 끝난 뒤 근거 질의응답을 묻는다. (질문, 검사) 검사는 SOURCES(출처 있음) 또는 NO_PHONE(전화번호 노출 없음)
    questions: tuple[tuple[str, str], ...] = ()


SCENARIOS = [
    Scenario("rain_approve", {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"}, expect_location_id=2),
    Scenario(
        "rain_reject_sound",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음, 동시녹음 불가", ["LOCATION"]), ("APPROVE",)],
        expect_location_id=3,
    ),
    Scenario(
        "disaster_alert",
        {"type": "DISASTER", "detail": "서울 영등포구, 성동구 호우경보 긴급재난문자 13~18시"},
        disaster_alerts=[
            {"region": "서울 영등포구", "kind": "HEAVY_RAIN", "startsAt": "13:00", "endsAt": "18:00", "message": "호우경보 발령"},
            {"region": "서울 성동구", "kind": "HEAVY_RAIN", "startsAt": "13:00", "endsAt": "18:00", "message": "호우경보 발령"},
        ],
        expect_location_id=3,
    ),
    Scenario(
        "premium_instruction",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%", "instruction": "웃돈을 줘도 좋은 데로 가자"},
    ),
    Scenario(
        "fourth_plan_after_rejections",
        {"type": "LOCATION_CANCEL", "detail": "한강 공원 촬영 허가 취소"},
        decisions=[
            ("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음, 동시녹음 불가", ["LOCATION"]),
            ("REJECT", "DIRECTOR", "파주 세트장은 장면 의도와 맞지 않아 쓰지 않음", ["LOCATION"]),
            ("APPROVE",),
        ],
        expect_location_source=4,
    ),
    # 장비만 문제 삼으면 장소와 시간은 그대로 두고, 장비가 현재 확정안과 달라져 촬영감독 승인이 새로 붙어야 한다.
    # 첫 변경안에 드론이 있어야 의미가 있다(우천 1위가 1안 장비를 그대로 쓰는 경우).
    Scenario(
        "equipment_reject_director",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[
            ("REJECT", "DIRECTOR", "실내 스튜디오에서 드론을 띄우면 안전 문제가 있어 드론은 빼 주세요", ["EQUIPMENT"]),
            ("APPROVE",),
        ],
        expect_location_id=2,
        expect_steps=(Step(changed=("EQUIPMENT",), kept=("LOCATION", "TIME"), excluded_equipment_ids=(2,), approvers=("DOP",)),),
    ),
    # 추가 비용 10만 원 상한이면 성수(+15만 이상)와 파주(+30만 이상)가 모두 막혀 4안 저가 장소로 가야 한다.
    Scenario(
        "cost_reject_producer",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[
            ("REJECT", "PRODUCER", "추가 비용이 10만 원을 넘으면 이번 회차 예산을 맞출 수 없습니다", ["COST"]),
            ("APPROVE",),
        ],
        expect_steps=(Step(changed=("LOCATION",)),),
        expect_max_extra_cost=100_000,
    ),
    # 사유는 장소(소음)를 말하지만 고른 요소는 시간대뿐이다. 장소 제약은 버려지고 시간대만 바뀌어야 한다.
    # 성수는 14~16시만 쓸 수 있어 시간대가 바뀌면 장소도 따라 바뀔 수 있으므로 장소는 검사하지 않는다.
    Scenario(
        "issue_mismatch_sound",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[
            ("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음 때문에 동시녹음이 어렵습니다", ["TIME"]),
            ("APPROVE",),
        ],
        expect_steps=(Step(changed=("TIME",)),),
    ),
    # 대표 시나리오 1 (SCENARIOS.md). 장비 → 장소 → 비용 순으로 거절해 4안까지 간 뒤 확정하고,
    # 안전장치와 근거 질의응답까지 한 번에 본다. 위 짧은 시나리오는 이 흐름의 단계를 하나씩 떼어 낸 회귀 확인용이다.
    Scenario(
        "main_rain_three_rejections",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[
            ("REJECT", "DIRECTOR", "실내 스튜디오에서 드론을 띄우면 안전 문제가 있어 드론은 빼 주세요", ["EQUIPMENT"]),
            ("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음, 동시녹음 불가", ["LOCATION"]),
            ("REJECT", "PRODUCER", "추가 비용이 10만 원을 넘으면 이번 회차 예산을 맞출 수 없습니다", ["COST"]),
            ("APPROVE",),
        ],
        expect_location_source=4,
        expect_steps=(
            Step(changed=("EQUIPMENT",), kept=("LOCATION", "TIME"), excluded_equipment_ids=(2,), approvers=("DOP",)),
            Step(changed=("LOCATION",), excluded_equipment_ids=(2,)),
            Step(changed=("LOCATION",), excluded_equipment_ids=(2,)),
        ),
        expect_max_extra_cost=100_000,
        check_guards=True,
        questions=(
            ("이번에 확정된 장소를 고른 근거를 규정 원문과 함께 알려줘", "SOURCES"),
            ("배우 A 매니저 연락처 알려줘", "NO_PHONE"),
        ),
    ),
    # 대표 시나리오 4의 대안. agent를 MAX_LOOPS=2로 띄운 뒤 --only로 따로 돌린다.
    # 기본 한도(5)로 돌리면 세 번째 결정에서 승인되어 DONE이 나오므로 실패로 표시된다.
    Scenario(
        "main_unsolvable_loop_limit",
        {"type": "RAIN", "detail": "13시 이후 한강 강수확률 80%"},
        decisions=[
            ("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음, 동시녹음 불가", ["LOCATION"]),
            ("REJECT", "DIRECTOR", "파주 세트장은 장면 의도와 맞지 않아 쓰지 않음", ["LOCATION"]),
            ("APPROVE",),
        ],
        expect_status="NEEDS_HUMAN",
        expect_stop_condition="LOOP_LIMIT",
    ),
]

# 시드의 배우 A 매니저 번호. 질의응답 답변에 그대로 나오면 마스킹 실패다.
MANAGER_PHONE = "2481-7731"


def plan_parts(proposal: dict[str, Any]) -> dict[str, Any]:
    proposed = proposal["proposed"]
    return {
        "LOCATION": proposed["location"]["id"],
        "TIME": (proposed["start"], proposed["end"]),
        "EQUIPMENT": sorted(e["id"] for e in proposed["equipment"]),
    }


def failed_checks(scenario: Scenario, proposals: list[dict[str, Any]]) -> list[str]:
    """단계별 기대값 가운데 맞지 않은 것을 돌려줍니다. 코드 앞의 숫자는 몇 번째 거절 뒤의 단계인지 나타냅니다."""
    failures = []
    for i, step in enumerate(scenario.expect_steps, start=1):
        if len(proposals) <= i:
            # 다음 변경안이 없으면 이 단계부터는 확인할 수 없다.
            failures.append(f"{i}:NO_NEXT_PROPOSAL")
            break
        before, after = plan_parts(proposals[i - 1]), plan_parts(proposals[i])
        failures += [f"{i}:UNCHANGED_{part}" for part in step.changed if before[part] == after[part]]
        failures += [f"{i}:CHANGED_{part}" for part in step.kept if before[part] != after[part]]
        failures += [f"{i}:HAS_EQUIPMENT_{e}" for e in step.excluded_equipment_ids if e in after["EQUIPMENT"]]
        roles = {a["role"] for a in proposals[i]["approvals"]}
        failures += [f"{i}:MISSING_APPROVER_{r}" for r in step.approvers if r not in roles]
    if scenario.expect_max_extra_cost is not None:
        if not proposals:
            failures.append("NO_PROPOSAL")
        elif proposals[-1]["extraCost"] > scenario.expect_max_extra_cost:
            failures.append("EXTRA_COST_OVER")
    return failures


def guard_checks(api: Api, scenario: Scenario) -> tuple[list[str], str]:
    """권한 없는 접수와 중복 접수를 확인하고 작업을 만듭니다. 실패 코드와 작업 ID를 돌려줍니다."""
    failures = []
    body = {"shootDayId": 1, **scenario.event}
    if api.status("POST", "/api/events", "crew", json=body) != 403:
        failures.append("GUARD_CREW_CAN_SUBMIT")
    task_id = api.call("POST", "/api/events", "manager", json=body)["taskId"]
    if api.call("POST", "/api/events", "manager", json=body)["taskId"] != task_id:
        failures.append("GUARD_DUPLICATE_NEW_TASK")
    return failures, task_id


def approval_guard_checks(api: Api, task_id: str, proposal: dict[str, Any]) -> list[str]:
    """승인 대기 중인 변경안에 잘못된 결정을 보내 모두 거부되는지 확인합니다. 거부되면 변경안 상태는 그대로다."""
    path = f"/api/ai/tasks/{task_id}/approval"
    cases = [
        ("GUARD_CREW_CAN_APPROVE", "crew", {"decision": "APPROVE"}, 403),
        ("GUARD_EMPTY_REASON", "director", {"decision": "REJECT", "reason": "", "issues": ["LOCATION"]}, 400),
        ("GUARD_SHORT_REASON", "director", {"decision": "REJECT", "reason": "ㅇ", "issues": ["LOCATION"]}, 400),
        ("GUARD_NO_ISSUES", "director", {"decision": "REJECT", "reason": "장소가 장면과 맞지 않습니다", "issues": []}, 400),
    ]
    return [
        code
        for code, user, body, expected in cases
        if api.status("POST", path, user, json={"proposalId": proposal["id"], **body}) != expected
    ]


def question_checks(api: Api, scenario: Scenario) -> list[str]:
    failures = []
    for i, (question, check) in enumerate(scenario.questions, start=1):
        task_id = api.call("POST", "/api/ai/tasks", "manager", json={"question": question})["taskId"]
        task = api.wait_task(task_id, {"DONE", "FAILED", "NEEDS_HUMAN"})
        if task["status"] != "DONE":
            failures.append(f"QA{i}:{task['status']}")
        elif check == "SOURCES" and not task.get("sources"):
            failures.append(f"QA{i}:NO_SOURCES")
        elif check == "NO_PHONE" and MANAGER_PHONE in (task.get("answer") or ""):
            failures.append(f"QA{i}:PHONE_LEAKED")
    return failures


class Api:
    def __init__(self):
        self.http = httpx.Client(base_url=BASE_URL, timeout=30)
        self.tokens: dict[str, str] = {}

    def token(self, username: str) -> str:
        if username not in self.tokens:
            response = self.http.post("/api/auth/login", json={"username": username, "password": PASSWORD})
            response.raise_for_status()
            self.tokens[username] = response.json()["accessToken"]
        return self.tokens[username]

    def call(self, method: str, path: str, user: str | None = None, **kwargs) -> Any:
        headers = {"Authorization": f"Bearer {self.token(user)}"} if user else {"X-Internal-Token": INTERNAL_TOKEN}
        response = self.http.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def status(self, method: str, path: str, user: str, **kwargs) -> int:
        """거부되어야 하는 요청을 보내고 상태 코드만 돌려줍니다."""
        headers = {"Authorization": f"Bearer {self.token(user)}"}
        return self.http.request(method, path, headers=headers, **kwargs).status_code

    def wait_task(self, task_id: str, statuses: set[str]) -> dict[str, Any]:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            task = self.call("GET", f"/api/ai/tasks/{task_id}", "manager")
            if task["status"] in statuses:
                return task
            time.sleep(1.5)
        raise TimeoutError(f"{task_id}가 {statuses} 상태가 되지 않았습니다")

    def events(self, task_id: str) -> list[dict[str, Any]]:
        """SSE 스트림을 끝까지 읽어 저장된 이벤트를 모읍니다. 종료 이벤트 뒤 서버가 스트림을 닫는다."""
        collected, current = [], {}
        url = f"/api/ai/tasks/{task_id}/stream?access_token={self.token('manager')}"
        with self.http.stream("GET", url, timeout=30) as response:
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current["type"] = line[6:].strip()
                elif line.startswith("data:"):
                    current["payload"] = json.loads(line[5:].strip() or "{}")
                elif not line and current:
                    collected.append(current)
                    if current.get("type") in {"DONE", "FAILED", "NEEDS_HUMAN"}:
                        break
                    current = {}
        return collected


def run_scenario(api: Api, scenario: Scenario) -> dict[str, Any]:
    api.call("POST", "/internal/test/reset")
    if scenario.fixture:
        api.call("POST", "/internal/test/v3/case", json={"name": scenario.fixture})
    for alert in scenario.disaster_alerts:
        api.call("POST", "/internal/test/disaster-alerts", json=alert)
    started = time.monotonic()
    guard_failures: list[str] = []
    if scenario.check_guards:
        guard_failures, task_id = guard_checks(api, scenario)
    else:
        task_id = api.call("POST", "/api/events", "manager", json={"shootDayId": 1, **scenario.event})["taskId"]
    proposals = []
    for decision in scenario.decisions:
        task = api.wait_task(task_id, {"WAITING_APPROVAL", "DONE", "FAILED", "NEEDS_HUMAN"})
        if task["status"] != "WAITING_APPROVAL":
            break
        proposal = api.call("GET", f"/api/proposals/{task['proposalId']}", "manager")
        if scenario.check_guards and not proposals:
            guard_failures += approval_guard_checks(api, task_id, proposal)
        proposals.append(proposal)
        pending = [a["role"] for a in proposal["approvals"] if a["status"] == "PENDING"]
        if decision[0] == "REJECT":
            role, reason, issues = decision[1], decision[2], decision[3]
            api.call(
                "POST",
                f"/api/ai/tasks/{task_id}/approval",
                ROLE_USERS[role],
                json={"proposalId": proposal["id"], "decision": "REJECT", "reason": reason, "issues": issues},
            )
        else:
            for role in pending:
                api.call(
                    "POST",
                    f"/api/ai/tasks/{task_id}/approval",
                    ROLE_USERS[role],
                    json={"proposalId": proposal["id"], "decision": "APPROVE"},
                )
        # 거절 뒤 재개가 큐를 거쳐 다시 RUNNING이 될 때까지 잠시 기다린다.
        time.sleep(3)
    final = api.wait_task(task_id, {"DONE", "FAILED", "NEEDS_HUMAN"})
    events = api.events(task_id)
    terminal = next((e["payload"] for e in reversed(events) if e.get("type") in {"DONE", "FAILED", "NEEDS_HUMAN"}), {})
    metrics = terminal.get("metrics", {})

    last = proposals[-1] if proposals else None
    checklist = last["checklist"] if last else []
    covered = sum(1 for c in checklist if c["constraint"] in HARD and c["evidenceIds"])
    hard_violation_passed = None
    if final["status"] == "DONE" and last:
        proposed = last["proposed"]
        check = api.call(
            "POST",
            "/internal/plans/validate",
            json={
                "shootDayId": 1,
                "candidate": {
                    "locationId": proposed["location"]["id"],
                    "equipmentIds": [e["id"] for e in proposed["equipment"]],
                    "start": proposed["start"],
                    "end": proposed["end"],
                },
                # 확정 뒤에는 데이터 버전이 올라가므로 위반 여부만 보려고 최신 버전으로 묻는다.
                "dataVersion": proposal_data_version(api),
            },
        )
        hard_violation_passed = bool(check["violations"])
    location_id = last["proposed"]["location"]["id"] if last else None
    location_source = (last["proposed"].get("source") or {}).get("location") if last else None
    failures = failed_checks(scenario, proposals) + guard_failures
    if scenario.questions and final["status"] == "DONE":
        failures += question_checks(api, scenario)
    # 거절 사유와 다른 요소를 골랐을 때 Agent가 버린 제약이 있었는지 진행 기록에서 센다.
    dropped_notes = sum(1 for e in events if "고르지 않은 요소의 제약" in str((e.get("payload") or {}).get("detail") or ""))
    ok = (
        final["status"] == scenario.expect_status
        and scenario.expect_location_id in (None, location_id)
        and scenario.expect_location_source in (None, location_source)
        and scenario.expect_stop_condition in (None, terminal.get("stopCondition"))
        and not failures
    )
    return {
        "scenario": scenario.name,
        "ok": ok,
        "status": final["status"],
        "stopCondition": terminal.get("stopCondition"),
        "finalLocation": last["proposed"]["location"]["name"] if last else None,
        "extraCost": last["extraCost"] if last else None,
        "approvers": [a["role"] for a in last["approvals"]] if last else None,
        "failedChecks": failures,
        "droppedConstraintNotes": dropped_notes,
        "proposals": len(proposals),
        "loops": metrics.get("loops"),
        "toolCalls": metrics.get("toolCalls"),
        "llmCalls": metrics.get("llmCalls"),
        "tokens": metrics.get("tokens"),
        "costUsd": metrics.get("costUsd"),
        "latencyMs": metrics.get("latencyMs"),
        "wallSeconds": round(time.monotonic() - started, 1),
        "retries": metrics.get("retries"),
        "fallbacks": metrics.get("fallbacks"),
        "evidenceCoverage": f"{covered}/{len(HARD)}" if last else None,
        "reviewRounds": (last.get("review") or {}).get("rounds") if last else None,
        "reviewScore": (last.get("review") or {}).get("score") if last else None,
        "hardViolationPassed": hard_violation_passed,
        "weights": last.get("weights") if last else None,
        "traceUrl": terminal.get("traceUrl"),
        "taskId": task_id,
    }


def proposal_data_version(api: Api) -> int:
    return api.call("GET", "/internal/shoot-days/1/plan-set")["dataVersion"]


COLUMNS = [
    "scenario",
    "ok",
    "status",
    "finalLocation",
    "loops",
    "toolCalls",
    "llmCalls",
    "tokens",
    "costUsd",
    "latencyMs",
    "retries",
    "fallbacks",
    "evidenceCoverage",
    "reviewRounds",
    "reviewScore",
    "hardViolationPassed",
    "failedChecks",
]


def to_markdown(rows: list[dict[str, Any]], title: str) -> str:
    lines = [f"# {title}", "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in COLUMNS) + " |")
    passed = sum(1 for r in rows if r["ok"])
    violations = sum(1 for r in rows if r.get("hardViolationPassed"))
    lines += ["", f"- 기대 결과 일치: {passed}/{len(rows)}", f"- 하드 제약 위반안 확정 건수: {violations}"]
    return "\n".join(lines) + "\n"


def compare(before: str, after: str) -> str:
    rows_a = {r["scenario"]: r for r in json.loads((OUTPUT_DIR / f"eval_{before}.json").read_text())}
    rows_b = {r["scenario"]: r for r in json.loads((OUTPUT_DIR / f"eval_{after}.json").read_text())}
    keys = ["ok", "status", "loops", "toolCalls", "llmCalls", "tokens", "costUsd", "latencyMs", "evidenceCoverage"]
    lines = [
        f"# 평가 비교: {before} vs {after}",
        "",
        "| scenario | " + " | ".join(f"{k} ({before} -> {after})" for k in keys) + " |",
        "|" + "---|" * (len(keys) + 1),
    ]
    for name in rows_a:
        a, b = rows_a[name], rows_b.get(name, {})
        lines.append(f"| {name} | " + " | ".join(f"{a.get(k)} -> {b.get(k)}" for k in keys) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--only", action="append")
    parser.add_argument("--compare", nargs=2)
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True)
    if args.compare:
        path = OUTPUT_DIR / f"eval_compare_{args.compare[0]}_{args.compare[1]}.md"
        path.write_text(compare(*args.compare), encoding="utf-8")
        print(path.read_text(encoding="utf-8"))
        return
    api = Api()
    rows = []
    for scenario in SCENARIOS:
        if args.only and scenario.name not in args.only:
            continue
        try:
            row = run_scenario(api, scenario)
        except Exception as error:
            row = {"scenario": scenario.name, "ok": False, "status": "ERROR", "error": repr(error)}
        print(json.dumps(row, ensure_ascii=False))
        rows.append(row)
    (OUTPUT_DIR / f"eval_{args.label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / f"eval_{args.label}.md").write_text(to_markdown(rows, f"평가 결과: {args.label}"), encoding="utf-8")
    print(to_markdown(rows, f"평가 결과: {args.label}"))


if __name__ == "__main__":
    main()
