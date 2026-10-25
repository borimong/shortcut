"""자체 검토(self_review) LLM 채점이 믿을 만한지 잽니다.

운영 노드 코드와 프롬프트를 그대로 부르고, 모델만 --model로 바꿀 수 있습니다. 두 부분으로 나눕니다.

  cases: 결함 주입 케이스(evals/review_judge_cases.py). 실제 입력 26개로 흠 없는 안(gold)을 쓰고 결함을 하나씩 넣었다.
         통과 판정 정확도, 결함 변형이 gold보다 낮은지, 겨냥한 항목이 깎였는지, 프롬프트 상한 규칙과 행동 선택을 본다.
  real:  실제 실행에서 복원한 self_review 입력(evals/review_judge_real.json)을 현재 프롬프트로 다시 채점한다.
         같은 입력을 여러 번 채점했을 때의 흔들림과, 금지한 감점 사유(예산 초과 오판, 비용과 거리 자체)를 본다.

실행(작업 폴더, safe_run 경유):
  python -m evals.review_judge --label 4o_mini
  python -m evals.review_judge --label 41_mini --model gpt-4.1-mini
  python -m evals.review_judge --compare 4o_mini 41_mini
  옵션: --part cases|real|all, --runs N(기본 3), --limit N, --concurrency N
결과: outputs/review_judge_{label}.json, .md
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
# 고치기 전 코드와 같은 케이스로 비교하려고 에이전트 코드 위치를 바꿀 수 있게 한다.
sys.path[:0] = [os.getenv("REVIEW_JUDGE_AGENT_DIR", str(ROOT / "agent"))]

from evals.review_judge_cases import REAL_PATH, Case, build_cases, build_holdout  # noqa: E402

OUTPUT_DIR = ROOT / "outputs"
ITEMS = ["evidence", "rejection", "optimization", "explanation", "risk"]
PASS_SCORE = 80
# 엔진이 예산 상한 이내라고 적어 준 안에서 예산 초과를 말하면 사실과 다른 감점이다.
OVER_BUDGET = re.compile(r"예산\s*(상한)?\s*(을|를)?\s*초과|상한을\s*넘|예산\s*경고")
# 비용이나 거리 자체를 깎은 이유로 든 피드백. 프롬프트는 고칠 수 없는 사실이라 피드백에 쓰지 말라고 한다.
COST_DISTANCE = re.compile(r"비용|거리")
# 설명이나 이유가 부족하다는 지적은 고칠 수 있는 감점이라 따로 센다.
NEGATIVE = re.compile(r"감점|부족|아쉽|높|길|많|크|부담|균형|불리")
NOT_DEDUCTED = re.compile(r"감점하지\s*않|감점 없|문제\s*없")
ABOUT_TEXT = re.compile(r"설명|이유|근거|언급|비교")


# constraint_citation의 도우미와 같다. 그 모듈을 가져오면 app이 기본 경로에서 먼저 로드되어 위 경로 지정이 듣지 않는다.
def load_env_keys(path: Path, keys: tuple[str, ...]) -> None:
    os.environ["LANGSMITH_TRACING"] = "false"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in keys and not os.getenv(key.strip()):
            os.environ[key.strip()] = value.strip().strip('"')


class NullEvents:
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        return None


def recording_model(model_cls):
    class RecordingModel(model_cls):
        async def structured(self, ctx, messages, schema):
            result = await super().structured(ctx, messages, schema)
            ctx.raw_structured = result.model_dump()
            return result

    return RecordingModel


def forbidden(feedback: list[str]) -> dict[str, bool]:
    def negative_cost(f: str) -> bool:
        return bool(COST_DISTANCE.search(f) and NEGATIVE.search(f) and not NOT_DEDUCTED.search(f))

    return {
        "over_budget": any(OVER_BUDGET.search(f) for f in feedback),
        "cost_distance": any(negative_cost(f) and not ABOUT_TEXT.search(f) for f in feedback),
        "cost_explain": any(negative_cost(f) and ABOUT_TEXT.search(f) for f in feedback),
    }


async def judge(state: dict[str, Any], deps: SimpleNamespace) -> dict[str, Any]:
    from app.graph import nodes
    from app.harness.limits import new_counter
    from app.runtime import RunContext

    state = copy.deepcopy(state)
    state["loop_counter"] = new_counter()
    ctx = RunContext("review-judge", "review-judge", deps.settings, deps.model, None, NullEvents())
    started = time.monotonic()
    update = await nodes.self_review(state, SimpleNamespace(context=ctx, store=None))
    # 점수, 통과 여부, 행동은 노드가 이력에 남긴 값을 쓴다. 모델 원본 답은 따로 남긴다.
    entry = update["review_history"][-1]
    counter = update["loop_counter"]
    return {
        "score": entry["score"],
        "passed": entry.get("passed", entry["score"] >= PASS_SCORE),
        "blocking": entry.get("blocking", []),
        "breakdown": entry["breakdown"],
        "feedback": entry.get("feedback", []),
        "action": entry.get("action"),
        "raw": getattr(ctx, "raw_structured", None),
        "review_next": update.get("review_next"),
        "tokens": counter["tokens"],
        "cost_usd": counter["cost_usd"],
        "fallbacks": counter["fallbacks"],
        "seconds": round(time.monotonic() - started, 1),
    }


def real_inputs(limit: int | None) -> list[dict[str, Any]]:
    """같은 입력이 여러 번 기록된 경우(같은 안을 회차마다 다시 채점) 하나만 남깁니다."""
    records = json.loads(REAL_PATH.read_text(encoding="utf-8"))
    seen: dict[str, dict] = {}
    for record in records:
        s = record["state"]
        key = json.dumps(
            [s["selected_plan"], s.get("last_rejection"), s.get("review_history")], ensure_ascii=False, sort_keys=True
        )
        seen.setdefault(key, record)
    # 체크포인트에 아직 없던 채널은 None으로 복원되므로, 운영 State처럼 키를 빼야 노드의 기본값이 쓰인다.
    items = [
        {
            "id": f"r{i:02d}",
            "thread_id": r["thread_id"],
            "state": {k: v for k, v in r["state"].items() if v is not None},
            "logged": r["logged"],
        }
        for i, r in enumerate(seen.values())
    ]
    return items[:limit] if limit else items


async def run_all(jobs: list[tuple[str, int, dict]], deps: SimpleNamespace, concurrency: int) -> dict[str, list]:
    gate = asyncio.Semaphore(concurrency)
    results: dict[str, list] = defaultdict(list)
    done = 0

    async def one(key: str, run: int, state: dict) -> None:
        nonlocal done
        async with gate:
            try:
                result = await judge(state, deps)
            except Exception as error:  # 한 건 실패로 전체 측정을 버리지 않는다.
                result = {"error": repr(error)}
            result["run"] = run
            results[key].append(result)
            done += 1
            if done % 25 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}", flush=True)

    await asyncio.gather(*(one(k, r, s) for k, r, s in jobs))
    return results


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def _rate(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def summarize_cases(cases: list[Case], results: dict[str, list]) -> dict[str, Any]:
    ok = {c.id: [r for r in results.get(c.id, []) if "error" not in r] for c in cases}
    mean_item = {cid: {k: _mean([r["breakdown"][k] for r in rs]) for k in ITEMS} for cid, rs in ok.items() if rs}
    mean_total = {cid: _mean([r["score"] for r in rs]) for cid, rs in ok.items() if rs}
    gold = {c.base: c.id for c in cases if c.variant == "gold"}
    by_variant: dict[str, list[Case]] = defaultdict(list)
    for c in cases:
        by_variant[c.variant].append(c)

    variants = {}
    for name, group in by_variant.items():
        runs = [r for c in group for r in ok[c.id]]
        row: dict[str, Any] = {
            "cases": len(group),
            "runs": len(runs),
            "mean_score": _mean([r["score"] for r in runs]),
            "pass_rate": _rate([r["passed"] for r in runs]),
            "items": {k: _mean([r["breakdown"][k] for r in runs]) for k in ITEMS},
        }
        expect = group[0].expect_pass
        if expect is not None:
            row["verdict_accuracy"] = _rate([r["passed"] == expect for r in runs])
        if name != "gold":
            pairs = [
                (mean_total[c.id], mean_total[gold[c.base]]) for c in group if c.id in mean_total and gold[c.base] in mean_total
            ]
            row["delta_vs_gold"] = _mean([a - b for a, b in pairs])
            row["abs_delta_vs_gold"] = _mean([abs(a - b) for a, b in pairs])
            row["lower_than_gold"] = _rate([a < b for a, b in pairs])
        target = group[0].target
        if target:
            drops = []
            biggest = []
            for c in group:
                if c.id not in mean_item or gold[c.base] not in mean_item:
                    continue
                delta = {k: mean_item[gold[c.base]][k] - mean_item[c.id][k] for k in ITEMS}
                drops.append(delta[target])
                biggest.append(delta[target] > 0 and delta[target] == max(delta.values()))
            row["target"] = target
            row["target_drop"] = _mean(drops)
            row["target_hit"] = _rate([d > 0 for d in drops])
            row["target_biggest"] = _rate(biggest)
        if group[0].caps:
            row["cap_kept"] = _rate([all(r["breakdown"][k] <= v for k, v in group[0].caps.items()) for r in runs])
        if group[0].expect_actions:
            row["action_match"] = _rate([r["action"] in group[0].expect_actions for r in runs])
        flags = [forbidden(r["feedback"]) for r in runs]
        row["fb_over_budget"] = _rate([f["over_budget"] for f in flags])
        row["fb_cost_distance"] = _rate([f["cost_distance"] for f in flags])
        row["fb_cost_explain"] = _rate([f["cost_explain"] for f in flags])
        variants[name] = row

    labelled = [(c, r) for c in cases if c.expect_pass is not None for r in ok[c.id]]
    should_pass = [r["passed"] for c, r in labelled if c.expect_pass]
    should_fail = [not r["passed"] for c, r in labelled if not c.expect_pass]
    spread = [statistics.pstdev([r["score"] for r in rs]) for rs in ok.values() if len(rs) > 1]
    flips = [len({r["passed"] for r in rs}) > 1 for rs in ok.values() if len(rs) > 1]
    return {
        "variants": variants,
        "overall": {
            "good_pass_rate": _rate(should_pass),
            "bad_fail_rate": _rate(should_fail),
            "balanced_accuracy": round((_rate(should_pass) + _rate(should_fail)) / 2, 3) if should_pass and should_fail else None,
            "mean_run_std": _mean(spread),
            "verdict_flip_rate": _rate(flips),
            "errors": sum(1 for rs in results.values() for r in rs if "error" in r),
        },
    }


def summarize_real(items: list[dict], results: dict[str, list]) -> dict[str, Any]:
    rows = []
    for item in items:
        rs = [r for r in results.get(item["id"], []) if "error" not in r]
        if not rs:
            continue
        scores = [r["score"] for r in rs]
        verdicts = [r["passed"] for r in rs]
        rows.append(
            {
                "id": item["id"],
                "logged": item["logged"]["score"],
                "scores": scores,
                "std": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
                "flip": len(set(verdicts)) > 1,
                "passes": verdicts,
                "range": max(scores) - min(scores),
                "flags": [forbidden(r["feedback"]) for r in rs],
            }
        )
    logged_flags = [forbidden(i["logged"]["feedback"]) for i in items]
    all_flags = [f for row in rows for f in row["flags"]]
    return {
        "inputs": len(rows),
        "mean_score": _mean([s for row in rows for s in row["scores"]]),
        "pass_rate": _rate([v for row in rows for v in row["passes"]]),
        "logged_mean_score": _mean([row["logged"] for row in rows]),
        "logged_pass_rate": _rate([row["logged"] >= PASS_SCORE for row in rows]),
        "mean_abs_diff_vs_logged": _mean([abs(statistics.fmean(row["scores"]) - row["logged"]) for row in rows]),
        "mean_run_std": _mean([row["std"] for row in rows]),
        "max_range": max((row["range"] for row in rows), default=None),
        "verdict_flip_rate": _rate([row["flip"] for row in rows]),
        "fb_over_budget": _rate([f["over_budget"] for f in all_flags]),
        "fb_cost_distance": _rate([f["cost_distance"] for f in all_flags]),
        "fb_cost_explain": _rate([f["cost_explain"] for f in all_flags]),
        "logged_fb_cost_explain": _rate([f["cost_explain"] for f in logged_flags]),
        "logged_fb_over_budget": _rate([f["over_budget"] for f in logged_flags]),
        "logged_fb_cost_distance": _rate([f["cost_distance"] for f in logged_flags]),
        "rows": [{k: v for k, v in row.items() if k != "flags"} for row in rows],
    }


def examples(cases: list[Case], results: dict[str, list], limit: int = 8) -> list[dict]:
    """gold 계열에서 금지한 감점 사유가 나온 피드백을 몇 개 모읍니다."""
    found = []
    for c in cases:
        if c.variant not in ("gold", "paraphrase", "anchor_low"):
            continue
        for r in results.get(c.id, []):
            for f in r.get("feedback", []):
                flag = forbidden([f])
                if any(flag.values()):
                    found.append({"case": c.id, "score": r["score"], "feedback": f})
    return found[:limit]


def write_report(label: str, payload: dict[str, Any]) -> None:
    lines = [
        f"# 자체 검토 채점 평가: {label}",
        "",
        f"- 모델: {payload['model']}, 케이스 묶음 {payload.get('set', 'main')}, 회당 반복 {payload['runs']}회, 통과 기준 {PASS_SCORE}점",
    ]
    lines.append(
        f"- 비용 ${payload['cost_usd']:.3f}, 토큰 {payload['tokens']:,}, 대체 모델 전환 {payload['fallbacks']}회, 걸린 시간 {payload['seconds']}초"
    )
    cs = payload.get("cases_summary")
    if cs:
        o = cs["overall"]
        lines += [
            "",
            "## A. 결함 주입 케이스",
            "",
            f"- 통과해야 하는 안의 통과율 {o['good_pass_rate']}, 떨어져야 하는 안의 탈락율 {o['bad_fail_rate']}, 균형 정확도 {o['balanced_accuracy']}",
            f"- 같은 입력 반복 채점의 평균 표준편차 {o['mean_run_std']}점, 반복하면 통과 여부가 바뀌는 케이스 비율 {o['verdict_flip_rate']}, 오류 {o['errors']}건",
            "",
            "| 변형 | 케이스 | 평균 점수 | 통과율 | 판정 정확도 | gold 대비 | gold보다 낮음 | 겨냥 항목 | 항목 하락 | 항목 깎임 | 가장 크게 깎임 | 상한 준수 | 행동 일치 | 예산 초과 오판 | 비용/거리 자체 감점 | 비용/거리 설명 부족 지적 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, r in cs["variants"].items():
            lines.append(
                "| "
                + " | ".join(
                    str(x if x is not None else "")
                    for x in [
                        name,
                        r["cases"],
                        r["mean_score"],
                        r["pass_rate"],
                        r.get("verdict_accuracy"),
                        r.get("delta_vs_gold"),
                        r.get("lower_than_gold"),
                        r.get("target"),
                        r.get("target_drop"),
                        r.get("target_hit"),
                        r.get("target_biggest"),
                        r.get("cap_kept"),
                        r.get("action_match"),
                        r["fb_over_budget"],
                        r["fb_cost_distance"],
                        r["fb_cost_explain"],
                    ]
                )
                + " |"
            )
        lines += [
            "",
            "항목별 평균 점수(각 20점 만점)",
            "",
            "| 변형 | " + " | ".join(ITEMS) + " |",
            "|---" * (len(ITEMS) + 1) + "|",
        ]
        for name, r in cs["variants"].items():
            lines.append(f"| {name} | " + " | ".join(str(r["items"][k]) for k in ITEMS) + " |")
        ex = payload.get("examples") or []
        if ex:
            lines += ["", "gold 계열에서 나온 금지 감점 사유 예시", ""]
            lines += [f"- {e['case']} ({e['score']}점): {e['feedback']}" for e in ex]
    rs = payload.get("real_summary")
    if rs:
        lines += [
            "",
            "## B. 실제 입력 재채점",
            "",
            f"- 서로 다른 입력 {rs['inputs']}개, 평균 점수 {rs['mean_score']} (기록 당시 {rs['logged_mean_score']}), 통과율 {rs['pass_rate']} (기록 당시 {rs['logged_pass_rate']})",
            f"- 기록 점수와의 평균 차이 {rs['mean_abs_diff_vs_logged']}점, 반복 채점 평균 표준편차 {rs['mean_run_std']}점, 최대 폭 {rs['max_range']}점, 통과 여부가 바뀌는 입력 비율 {rs['verdict_flip_rate']}",
            f"- 예산 초과 오판 피드백 {rs['fb_over_budget']} (기록 당시 {rs['logged_fb_over_budget']}), 비용/거리 자체 감점 {rs['fb_cost_distance']} (기록 당시 {rs['logged_fb_cost_distance']}), 비용/거리 설명 부족 지적 {rs['fb_cost_explain']} (기록 당시 {rs['logged_fb_cost_explain']})",
        ]
    lines += [
        "",
        "참고: 결함 주입 케이스와 정답(통과 여부, 겨냥 항목)은 Claude가 실제 입력을 바탕으로 만든 합성 자료이며 팀 검수 전 참고치입니다.",
        "금지 감점 사유는 정규식으로 셉니다. 비용/거리 자체 감점은 '비용, 거리'와 부정 표현이 함께 나오고 설명, 이유, 근거 언급이 없는 피드백이고, 설명 부족 지적은 그 언급이 있는 피드백입니다(gold는 비용 증가 이유를 이미 적었습니다).",
    ]
    (OUTPUT_DIR / f"review_judge_{label}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare(labels: list[str]) -> None:
    data = [json.loads((OUTPUT_DIR / f"review_judge_{name}.json").read_text(encoding="utf-8")) for name in labels]
    keys = [
        ("모델", lambda d: d["model"]),
        ("통과해야 하는 안 통과율", lambda d: d["cases_summary"]["overall"]["good_pass_rate"]),
        ("떨어져야 하는 안 탈락율", lambda d: d["cases_summary"]["overall"]["bad_fail_rate"]),
        ("균형 정확도", lambda d: d["cases_summary"]["overall"]["balanced_accuracy"]),
        ("반복 채점 표준편차(케이스)", lambda d: d["cases_summary"]["overall"]["mean_run_std"]),
        ("통과 여부 뒤집힘(케이스)", lambda d: d["cases_summary"]["overall"]["verdict_flip_rate"]),
        ("gold 평균 점수", lambda d: d["cases_summary"]["variants"]["gold"]["mean_score"]),
        ("gold 비용/거리 자체 감점", lambda d: d["cases_summary"]["variants"]["gold"]["fb_cost_distance"]),
        ("gold 비용/거리 설명 부족 지적", lambda d: d["cases_summary"]["variants"]["gold"]["fb_cost_explain"]),
        ("실제 입력 통과율", lambda d: d["real_summary"]["pass_rate"]),
        ("실제 입력 표준편차", lambda d: d["real_summary"]["mean_run_std"]),
        ("실제 입력 비용/거리 감점", lambda d: d["real_summary"]["fb_cost_distance"]),
        ("비용(USD)", lambda d: round(d["cost_usd"], 3)),
    ]
    lines = [
        f"# 자체 검토 채점 비교: {' vs '.join(labels)}",
        "",
        "| 지표 | " + " | ".join(labels) + " |",
        "|---" * (len(labels) + 1) + "|",
    ]
    for name, fn in keys:
        values = []
        for d in data:
            try:
                values.append(str(fn(d)))
            except (KeyError, TypeError):
                values.append("")
        lines.append(f"| {name} | " + " | ".join(values) + " |")
    path = OUTPUT_DIR / f"review_judge_compare_{'_'.join(labels)}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path.read_text(encoding="utf-8"))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--model")
    parser.add_argument("--part", choices=["cases", "real", "all"], default="all")
    parser.add_argument("--set", choices=["main", "holdout"], default="main", help="결함 주입 케이스 묶음")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--compare", nargs="+")
    args = parser.parse_args()
    if args.compare:
        compare(args.compare)
        return
    if not args.label:
        parser.error("--label이 필요합니다")

    load_env_keys(ROOT / ".env", ("OPENAI_API_KEY", "OPENAI_MODEL", "FALLBACK_MODEL"))
    from app.config import Settings
    from app.harness.model import ModelGateway

    settings = Settings.from_env()
    model_name = args.model or settings.openai_model
    print(f"에이전트 코드: {sys.modules['app'].__file__}")
    deps = SimpleNamespace(settings=settings, model=recording_model(ModelGateway).openai(model_name, settings.fallback_model))

    builder = build_holdout if args.set == "holdout" else build_cases
    cases = builder() if args.part in ("cases", "all") else []
    if args.limit:
        bases = sorted({c.base for c in cases})[: args.limit]
        cases = [c for c in cases if c.base in bases]
    items = real_inputs(args.limit) if args.part in ("real", "all") else []
    jobs = [(c.id, run, c.state) for c in cases for run in range(args.runs)]
    jobs += [(i["id"], run, i["state"]) for i in items for run in range(args.runs)]
    print(f"모델 {model_name}, 케이스 {len(cases)}개, 실제 입력 {len(items)}개, 호출 {len(jobs)}회")

    started = time.monotonic()
    results = await run_all(jobs, deps, args.concurrency)
    every = [r for rs in results.values() for r in rs if "error" not in r]
    payload: dict[str, Any] = {
        "label": args.label,
        "model": model_name,
        "runs": args.runs,
        "set": args.set,
        "seconds": round(time.monotonic() - started, 1),
        "tokens": sum(r["tokens"] for r in every),
        "cost_usd": sum(r["cost_usd"] for r in every),
        "fallbacks": sum(r["fallbacks"] for r in every),
    }
    if cases:
        payload["cases_summary"] = summarize_cases(cases, results)
        payload["examples"] = examples(cases, results)
    if items:
        payload["real_summary"] = summarize_real(items, results)
    payload["cases"] = [
        {
            "id": c.id,
            "base": c.base,
            "variant": c.variant,
            "target": c.target,
            "expect_pass": c.expect_pass,
            "results": results.get(c.id, []),
        }
        for c in cases
    ]
    payload["real"] = [
        {"id": i["id"], "thread_id": i["thread_id"], "logged": i["logged"], "results": results.get(i["id"], [])} for i in items
    ]
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"review_judge_{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_report(args.label, payload)
    print((OUTPUT_DIR / f"review_judge_{args.label}.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
