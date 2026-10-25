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
# 승인 대기까지 LLM 호출이 여러 번 이어지고, 확정 뒤에는 실행팀(3단계, Agent 최대 6개)이 더 돌아서 넉넉히 기다린다.
WAIT_SECONDS = 360


@dataclass
class Scenario:
    name: str
    event: dict[str, Any]
    # 루프마다 내릴 결정. ("REJECT", 역할, 사유, 문제 요소 목록) 또는 ("APPROVE",)
    decisions: list[tuple] = field(default_factory=lambda: [("APPROVE",)])
    disaster_alerts: list[dict[str, Any]] = field(default_factory=list)
    expect_status: str = "DONE"
    expect_location_id: int | None = None
    # 최종 안의 장소가 몇 안에서 왔는지. 4면 1/2/3안 밖의 대체 장소다.
    expect_location_source: int | None = None
    # 실행팀 결과. 확정까지 간 시나리오는 실행도 끝나야 한다(DONE). 실패 시연은 NEEDS_HUMAN을 기대한다
    expect_exec_status: str | None = "DONE"
    # 실행팀에서 실행되면 안 되는 Agent(예: 장소 예약 실패 뒤의 연락)
    forbid_exec_agents: tuple[str, ...] = ()
    # 시나리오 동안 켤 관리자 설정(실패 시연 플래그). 끝나면 원래 값으로 되돌린다
    settings: dict[str, Any] = field(default_factory=dict)


SCENARIOS = [
    Scenario("rain_approve", {"type": "RAIN", "detail": "13시 이후 한강 시간당 8mm 비 예보"}, expect_location_id=2),
    Scenario(
        "rain_reject_sound",
        {"type": "RAIN", "detail": "13시 이후 한강 시간당 8mm 비 예보"},
        decisions=[("REJECT", "SOUND", "성수 스튜디오 오후 공사 소음, 동시녹음 불가", ["LOCATION"]), ("APPROVE",)],
        # 장소 문제로 거절되면 남은 파주(3안)보다 먼저 대체 장소를 찾으므로 4안 장소가 확정된다.
        expect_location_source=4,
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
        {"type": "RAIN", "detail": "13시 이후 한강 시간당 8mm 비 예보", "instruction": "웃돈을 줘도 좋은 데로 가자"},
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
    Scenario(
        "exec_venue_conflict",
        {"type": "RAIN", "detail": "13시 이후 한강 시간당 8mm 비 예보"},
        settings={"mockVenueConflict": True},
        expect_status="NEEDS_HUMAN",
        expect_exec_status="NEEDS_HUMAN",
        # 장소가 확정되지 않았으므로 허가, 차량, 연락, 장부는 실행되면 안 된다.
        forbid_exec_agents=("permit", "transport", "contact", "ledger"),
    ),
]


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

    def wait_task(self, task_id: str, statuses: set[str]) -> dict[str, Any]:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            task = self.call("GET", f"/api/ai/tasks/{task_id}", "pd")
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


def apply_settings(api: Api, changes: dict[str, Any]) -> dict[str, Any]:
    """관리자 설정을 바꾸고 바꾸기 전 값을 돌려줍니다."""
    current = api.call("GET", "/api/admin/settings", "pd")
    keys = ("maxLoops", "rainBlockMm", "rainWarnMm", "rainAlertLeadHours", "mockVenueConflict", "mockPermitDenied")
    api.call("PUT", "/api/admin/settings", "pd", json={**{k: current[k] for k in keys}, **changes})
    return {k: current[k] for k in changes}


def run_scenario(api: Api, scenario: Scenario) -> dict[str, Any]:
    previous = apply_settings(api, scenario.settings) if scenario.settings else {}
    try:
        return _run_scenario(api, scenario)
    finally:
        if previous:
            apply_settings(api, previous)


def _run_scenario(api: Api, scenario: Scenario) -> dict[str, Any]:
    api.call("POST", "/internal/test/reset")
    for alert in scenario.disaster_alerts:
        api.call("POST", "/internal/test/disaster-alerts", json=alert)
    started = time.monotonic()
    created = api.call("POST", "/api/events", "pd", json={"shootDayId": 1, **scenario.event})
    task_id = created["taskId"]
    proposals = []
    for decision in scenario.decisions:
        task = api.wait_task(task_id, {"WAITING_APPROVAL", "DONE", "FAILED", "NEEDS_HUMAN"})
        if task["status"] != "WAITING_APPROVAL":
            break
        proposal = api.call("GET", f"/api/proposals/{task['proposalId']}", "pd")
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
    execution = terminal.get("execution") or {}
    exec_reports = execution.get("reports") or []
    exec_done = [r["agent"] for r in exec_reports if r["status"] == "DONE"]
    location_id = last["proposed"]["location"]["id"] if last else None
    location_source = (last["proposed"].get("source") or {}).get("location") if last else None
    ok = (
        final["status"] == scenario.expect_status
        and scenario.expect_location_id in (None, location_id)
        and scenario.expect_location_source in (None, location_source)
        and (scenario.expect_exec_status is None or execution.get("status") == scenario.expect_exec_status)
        and not set(scenario.forbid_exec_agents) & {r["agent"] for r in exec_reports}
    )
    return {
        "scenario": scenario.name,
        "ok": ok,
        "status": final["status"],
        "stopCondition": terminal.get("stopCondition"),
        "finalLocation": last["proposed"]["location"]["name"] if last else None,
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
        "execStatus": execution.get("status"),
        "execDone": ",".join(exec_done),
        "execSkipped": ",".join(execution.get("skipped") or []),
        "execBudgetRemaining": (execution.get("budget") or {}).get("remainingKrw"),
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
    "execStatus",
    "execDone",
    "execSkipped",
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
