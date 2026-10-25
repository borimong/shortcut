"""제약 수집(collect_constraints)이 범주마다 인용한 근거가 실제로 맞는지 잽니다.

운영 노드 코드와 운영 모델을 그대로 쓰고, rag-mcp만 메모리 저장소로 띄웁니다.
코퍼스는 운영 문서 8개(base)와 평가용 확장 문서를 더한 것(full) 중에서 고릅니다.
정답은 조항 라벨(evals/constraint_labels/*.json)과 시나리오의 배우, 장소, 상황 키로 계산합니다.

  조항이 범주 c의 정답(관대) = 라벨 cats에 c가 있고, 적용 범위(배우의 현재 계약서, 후보 장소)가 맞다
  조항이 범주 c의 정답(엄격) = 관대 정답이면서, 상황 키가 붙은 조항이면 시나리오 상황과 겹친다

실행(작업 폴더, safe_run 경유):
  python -m evals.constraint_citation --corpus full --label full
  python -m evals.constraint_citation --corpus base --scenarios base --label base
  옵션: --limit N, --concurrency N, --check(색인과 라벨만 확인하고 모델은 부르지 않음)
결과: outputs/constraint_citation_{label}.json, .md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "mcp" / "rag-mcp")]

from fastmcp import Client  # noqa: E402

from app.graph.nodes import EVIDENCE_TYPES, NO_DISASTER_ALERT_ID, counts_as_evidence  # noqa: E402
from evals.constraint_scenarios import LOCATIONS, Scenario, build_scenarios  # noqa: E402
from rag_mcp.chunking import parse_markdown, split_into_chunks  # noqa: E402
from rag_mcp.embedding import OpenAIEmbedder  # noqa: E402
from rag_mcp.server import build_server  # noqa: E402
from rag_mcp.store import MemoryStore  # noqa: E402

BASE_CORPUS = ROOT / "mcp" / "rag-mcp" / "corpus"
EXTRA_CORPUS = Path(__file__).resolve().parent / "constraint_corpus"
LABEL_DIR = Path(__file__).resolve().parent / "constraint_labels"
OUTPUT_DIR = ROOT / "outputs"

CATEGORIES = ["CONTRACT", "SCHEDULE", "LAW", "BUDGET", "NO_FLY_ZONE", "DISASTER", "WEATHER"]


def load_env_keys(path: Path, keys: tuple[str, ...]) -> None:
    """.env에서 필요한 값만 읽습니다. LangSmith 설정까지 읽으면 평가 호출 수백 건이 trace로 올라가므로 고른다.
    .env가 없으면(새로 받은 저장소) 환경 변수에 이미 있는 값을 그대로 씁니다."""
    os.environ["LANGSMITH_TRACING"] = "false"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in keys and not os.getenv(key.strip()):
            os.environ[key.strip()] = value.strip().strip('"')


def load_corpus(kind: str) -> list:
    paths = sorted(BASE_CORPUS.glob("*.md"))
    if kind == "full":
        paths += sorted(EXTRA_CORPUS.glob("*.md"))
    return [parse_markdown(p.read_text(encoding="utf-8")) for p in paths]


def load_labels() -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for path in sorted(LABEL_DIR.glob("*.json")):
        for doc_id, value in json.loads(path.read_text(encoding="utf-8")).items():
            if doc_id in labels:
                raise ValueError(f"라벨 중복: {doc_id} ({path.name})")
            labels[doc_id] = value
    return labels


def chunk_table(documents: list, labels: dict[str, dict]) -> tuple[dict[str, dict], list]:
    """chunk_id마다 문서 종류, 범주, 상황 키, 적용 범위를 붙입니다. 라벨이 없는 조항이 있으면 멈춥니다."""
    table, chunks_by_doc, problems = {}, [], []
    for document in documents:
        label = labels.get(document.doc_id)
        if label is None:
            problems.append(f"{document.doc_id}: 문서 라벨 없음")
            continue
        chunks = split_into_chunks(document)
        chunks_by_doc.append((document, chunks))
        for chunk in chunks:
            section = label["sections"].get(chunk.heading)
            if section is None:
                problems.append(f"{document.doc_id}: '{chunk.heading}' 조항 라벨 없음")
                continue
            scope = dict(label.get("scope") or {})
            if section.get("locations"):
                scope["locations"] = section["locations"]
            table[chunk.chunk_id] = {
                "doc_id": document.doc_id,
                "doc_type": document.doc_type,
                "heading": chunk.heading,
                "cats": set(section.get("cats") or []),
                "topics": set(section.get("topics") or []),
                "scope": scope,
            }
    if problems:
        raise ValueError("라벨 확인 실패:\n" + "\n".join(problems))
    return table, chunks_by_doc


def in_scope(info: dict, scenario: Scenario) -> bool:
    scope = info["scope"]
    if "actor" in scope:
        return scope["actor"] in scenario.actors and scope.get("current", True)
    if "locations" in scope:
        return bool(set(scope["locations"]) & set(scenario.locations))
    return True


def is_gold(info: dict, category: str, scenario: Scenario, strict: bool) -> bool:
    if category not in info["cats"] or not in_scope(info, scenario):
        return False
    return not strict or not info["topics"] or bool(info["topics"] & set(scenario.topics))


def error_kind(info: dict, category: str) -> str:
    """틀린 인용을 원인별로 나눕니다. 범주는 맞는데 대상이 다르면 scope, 범주 자체가 다르면 content."""
    if category in info["cats"]:
        return "scope"
    return "content"


async def build_index(documents: list, chunks_by_doc: list) -> tuple[MemoryStore, OpenAIEmbedder]:
    """index_document 도구와 같은 입력(제목, 조항 제목, 원문)으로 임베딩해 메모리 저장소에 넣습니다."""
    embedder = OpenAIEmbedder()
    store = MemoryStore()
    for document, chunks in chunks_by_doc:
        texts = [f"{document.title}\n{c.heading}\n{c.text}" for c in chunks]
        vectors = await asyncio.to_thread(embedder.embed, texts)
        store.upsert(document, chunks, vectors, embedder.model)
    return store, embedder


class NullEvents:
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        return None


def recording_model(model_cls):
    """구조화 출력 원본을 ctx에 남겨, 코드가 걸러 내기 전 모델이 적은 근거 ID까지 볼 수 있게 합니다."""

    class RecordingModel(model_cls):
        async def structured(self, ctx, messages, schema):
            result = await super().structured(ctx, messages, schema)
            ctx.raw_structured = result.model_dump()
            return result

    return RecordingModel


async def run_scenario(scenario: Scenario, deps: SimpleNamespace) -> dict:
    """그래프의 after_collect 분기처럼, 근거가 빠진 범주가 있으면 info_retries < 2 동안 한 번 더 실행합니다."""
    from app.graph import nodes
    from app.harness.limits import new_counter
    from app.runtime import RunContext

    # 노드는 후보 장소를 1/2/3안에서 읽으므로, 시나리오의 첫 장소를 현재 확정안으로 두고 1/2/3안을 만든다.
    names = [LOCATIONS[loc][0] for loc in scenario.locations]
    state: dict[str, Any] = {
        "event": scenario.event,
        "plan_set": {
            "current": {"location": {"name": names[0]}},
            "options": [{"optionNo": i + 1, "location": {"name": name}} for i, name in enumerate(names)],
        },
        "impacted_entities": {"contract_doc_ids": scenario.contract_doc_ids, "risks": scenario.risks},
        "conditions": {"disaster_alerts": {"alerts": scenario.alerts}},
        "loop_counter": new_counter(),
    }
    rounds = []
    started = time.monotonic()
    while True:
        ctx = RunContext(scenario.id, scenario.id, deps.settings, deps.model, deps.tools, NullEvents())
        update = await nodes.collect_constraints(state, SimpleNamespace(context=ctx, store=None))
        state.update(update)
        raw = getattr(ctx, "raw_structured", {}) or {}
        rounds.append(
            {
                "missing_info": update["missing_info"],
                "hard_constraints": update["hard_constraints"],
                "raw_findings": raw.get("findings", []),
                "evidence_ids": sorted(update["evidence"]),
            }
        )
        if not (update["missing_info"] and state["info_retries"] < 2):
            break
    counter = state["loop_counter"]
    return {
        "scenario": scenario.to_dict(),
        "rounds": rounds,
        "evidence": {
            cid: {k: hit.get(k) for k in ("doc_id", "doc_type", "heading", "locations", "score")}
            for cid, hit in state["evidence"].items()
        },
        "tool_calls": counter["tool_calls"],
        "tokens": counter["tokens"],
        "cost_usd": counter["cost_usd"],
        "seconds": round(time.monotonic() - started, 1),
    }


def score(result: dict, table: dict[str, dict], scenario: Scenario) -> dict:
    """범주마다 최종 인용을 정답과 비교하고, 문서 종류 규칙이 모델 인용에서 지운 것도 셉니다."""
    final = result["rounds"][-1]
    retrieved = set(result["evidence"])
    # 재난 문자 조회 결과는 문서 조항이 아니라 라벨 표에 없습니다. 발령된 재난 문자가 없는 시나리오에서만
    # DISASTER의 정답 근거이고, 다른 범주나 재난 문자가 있는 시나리오에서는 근거가 아닙니다.
    data_cats = set() if scenario.alerts else {"DISASTER"}
    table = {**table, NO_DISASTER_ALERT_ID: {"doc_type": "DATA", "cats": data_cats, "topics": set(), "scope": {}}}
    cited_by_cat = {f["constraint"]: f["evidence_ids"] for f in final["hard_constraints"]}
    raw_by_cat: dict[str, list[str]] = defaultdict(list)
    for finding in final["raw_findings"]:
        raw_by_cat[finding["constraint"]].extend(finding.get("evidence_ids") or [])

    per_cat = {}
    for category in CATEGORIES:
        cited = list(dict.fromkeys(cited_by_cat.get(category, [])))
        gold = {cid for cid, info in table.items() if is_gold(info, category, scenario, strict=False)}
        gold_strict = {cid for cid, info in table.items() if is_gold(info, category, scenario, strict=True)}
        citations = []
        for cid in cited:
            info = table[cid]
            correct = cid in gold
            citations.append(
                {
                    "chunk_id": cid,
                    "correct": correct,
                    "correct_strict": cid in gold_strict,
                    "type_ok": info["doc_type"] in EVIDENCE_TYPES[category],
                    "error": None if correct else error_kind(info, category),
                }
            )
        kept = [c for c in citations if c["type_ok"]]
        # 모델은 적었지만 노드의 문서 종류 규칙이 지운 인용이다. 검색한 적 없는 ID는 hallucinated로 따로 센다.
        removed = [
            {"chunk_id": cid, "correct": cid in gold}
            for cid in dict.fromkeys(raw_by_cat.get(category, []))
            if cid in retrieved and cid not in cited and not counts_as_evidence(category, result["evidence"][cid])
        ]
        per_cat[category] = {
            "cited": len(citations),
            "correct": sum(c["correct"] for c in citations),
            "correct_strict": sum(c["correct_strict"] for c in citations),
            "citations": citations,
            "hallucinated": [cid for cid in raw_by_cat.get(category, []) if cid not in retrieved],
            "type_removed": removed,
            "gold": len(gold),
            "gold_retrieved": len(gold & retrieved),
            "gold_strict_retrieved": len(gold_strict & retrieved),
            "outcome": outcome(citations, gold, retrieved),
            "outcome_strict": outcome([c | {"correct": c["correct_strict"]} for c in citations], gold_strict, retrieved),
            "outcome_rule": outcome(kept, gold, retrieved),
        }
    return per_cat


def outcome(citations: list[dict], gold: set[str], retrieved: set[str]) -> str:
    """시스템 판단(근거 있음, 빠짐)과 실제 정답을 맞대어 한 단어로 나눕니다."""
    if citations:
        right = sum(c["correct"] for c in citations)
        if right == len(citations):
            return "clean"
        return "mixed" if right else "false_cover"
    if not gold:
        return "true_missing"
    return "missed_llm" if gold & retrieved else "missed_retrieval"


def summarize(scored: list[dict]) -> dict:
    """시나리오별 채점 결과를 범주별, 원인별 지표로 모읍니다."""

    def rates(key: str) -> dict:
        overall = Counter()
        by_cat: dict[str, Counter] = {c: Counter() for c in CATEGORIES}
        for item in scored:
            for category, value in item["per_cat"].items():
                overall[value[key]] += 1
                by_cat[category][value[key]] += 1
        return {"overall": dict(overall), "by_category": {c: dict(v) for c, v in by_cat.items()}}

    citations = [c | {"category": cat} for item in scored for cat, v in item["per_cat"].items() for c in v["citations"]]
    wrong = [c for c in citations if not c["correct"]]
    right = [c for c in citations if c["correct"]]
    return {
        "scenarios": len(scored),
        "categories_total": len(scored) * len(CATEGORIES),
        "citations": len(citations),
        "citation_precision": round(len(right) / len(citations), 4) if citations else None,
        "citation_precision_strict": round(sum(c["correct_strict"] for c in citations) / len(citations), 4)
        if citations
        else None,
        "wrong_by_error": dict(Counter(c["error"] for c in wrong)),
        "wrong_by_category": dict(Counter(c["category"] for c in wrong)),
        "rule_removes_wrong": sum(not c["type_ok"] for c in wrong),
        "rule_removes_right": sum(not c["type_ok"] for c in right),
        "type_removed_wrong": sum(not r["correct"] for i in scored for v in i["per_cat"].values() for r in v["type_removed"]),
        "type_removed_right": sum(r["correct"] for i in scored for v in i["per_cat"].values() for r in v["type_removed"]),
        "hallucinated_ids": sum(len(v["hallucinated"]) for item in scored for v in item["per_cat"].values()),
        "outcome": rates("outcome"),
        "outcome_strict": rates("outcome_strict"),
        "outcome_rule": rates("outcome_rule"),
        "rounds": dict(Counter(len(item["rounds"]) for item in scored)),
        "tool_calls_avg": round(sum(item["tool_calls"] for item in scored) / len(scored), 2),
        "cost_usd": round(sum(item["cost_usd"] for item in scored), 4),
        "seconds_avg": round(sum(item["seconds"] for item in scored) / len(scored), 1),
    }


def wrong_examples(scored: list[dict], table: dict[str, dict], limit: int = 40) -> list[dict]:
    rows = []
    for item in scored:
        for category, value in item["per_cat"].items():
            for c in value["citations"]:
                if not c["correct"]:
                    info = table[c["chunk_id"]]
                    rows.append(
                        {
                            "scenario": item["id"],
                            "category": category,
                            "chunk_id": c["chunk_id"],
                            "doc_type": info["doc_type"],
                            "heading": info["heading"],
                            "error": c["error"],
                            "type_ok": c["type_ok"],
                        }
                    )
    return rows[:limit]


def render_markdown(label: str, args: argparse.Namespace, corpus_info: dict, summary: dict, examples: list[dict]) -> str:
    lines = [f"# 제약 수집 근거 인용 평가 ({label})", ""]
    lines += [
        f"- 코퍼스: {args.corpus}, 문서 {corpus_info['documents']}개, 조항 {corpus_info['chunks']}개",
        f"- 시나리오 {summary['scenarios']}개, 범주 판정 {summary['categories_total']}건, 인용 {summary['citations']}건",
        f"- 모델 {os.getenv('OPENAI_MODEL')}, 대체 {os.getenv('FALLBACK_MODEL')}, 임베딩 {corpus_info['embedding_model']}",
        f"- 실행 횟수 분포(라운드 수: 시나리오 수) {summary['rounds']}, 평균 도구 호출 {summary['tool_calls_avg']}회, "
        f"평균 {summary['seconds_avg']}초, 비용 ${summary['cost_usd']}",
        "",
        "## 인용 정확도",
        "",
        f"- 인용 정밀도(관대): {summary['citation_precision']}",
        f"- 인용 정밀도(엄격, 상황까지 맞아야 정답): {summary['citation_precision_strict']}",
        f"- 틀린 인용 원인: {summary['wrong_by_error']} (scope: 범주는 맞지만 다른 배우나 장소, 옛 버전 / content: 그 범주 내용이 아님)",
        f"- 틀린 인용 범주: {summary['wrong_by_category']}",
        f"- 모델이 적었지만 검색한 적 없어 코드가 버린 ID: {summary['hallucinated_ids']}건",
        "",
        "## 범주 판정 결과 (관대 기준)",
        "",
        "clean: 인용 전부 정답 / mixed: 정답과 오답 섞임 / false_cover: 인용이 있지만 전부 오답(근거 있음으로 잘못 통과) / "
        "missed_llm: 정답이 검색됐는데 인용 안 함 / missed_retrieval: 정답이 검색되지 않음 / true_missing: 정답이 없어 비운 것",
        "",
        "| 범주 | clean | mixed | false_cover | missed_llm | missed_retrieval | true_missing |",
        "|---|---|---|---|---|---|---|",
    ]
    keys = ["clean", "mixed", "false_cover", "missed_llm", "missed_retrieval", "true_missing"]
    for category in CATEGORIES + ["전체"]:
        row = summary["outcome"]["overall"] if category == "전체" else summary["outcome"]["by_category"][category]
        lines.append(f"| {category} | " + " | ".join(str(row.get(k, 0)) for k in keys) + " |")
    lines += [
        "",
        f"엄격 기준 전체: {summary['outcome_strict']['overall']}",
        "",
        "## 노드의 문서 종류 규칙(EVIDENCE_TYPES)",
        "",
        f"- 모델 인용에서 실제로 지운 것: 오답 {summary['type_removed_wrong']}건, 정답 {summary['type_removed_right']}건",
        f"- 남은 인용 가운데 규칙에 걸리는 것(0이어야 함): 오답 {summary['rule_removes_wrong']}건, "
        f"정답 {summary['rule_removes_right']}건",
        "",
        "## 틀린 인용 예시",
        "",
        "| 시나리오 | 범주 | 조항 | 문서 종류 | 원인 | 규칙 통과 |",
        "|---|---|---|---|---|---|",
    ]
    for row in examples:
        lines.append(
            f"| {row['scenario']} | {row['category']} | {row['chunk_id']} {row['heading']} | {row['doc_type']} | "
            f"{row['error']} | {'예' if row['type_ok'] else '아니오'} |"
        )
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", choices=["base", "full"], default="full")
    parser.add_argument("--scenarios", choices=["all", "base"], default="all")
    parser.add_argument("--label", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    load_env_keys(ROOT / ".env", ("OPENAI_API_KEY", "OPENAI_MODEL", "FALLBACK_MODEL"))
    documents = load_corpus(args.corpus)
    table, chunks_by_doc = chunk_table(documents, load_labels())
    scenarios = build_scenarios()
    if args.scenarios == "base":
        scenarios = scenarios[:30]
    scenarios = scenarios[: args.limit] if args.limit else scenarios
    no_gold = Counter(c for s in scenarios for c in CATEGORIES if not any(is_gold(i, c, s, strict=False) for i in table.values()))
    print(f"문서 {len(documents)}개, 조항 {len(table)}개, 시나리오 {len(scenarios)}개, 정답 없는 범주 {dict(no_gold)}")
    if args.check:
        return

    from app.config import Settings
    from app.harness.model import ModelGateway
    from app.harness.tools import ToolGateway

    store, embedder = await build_index(documents, chunks_by_doc)
    settings = Settings.from_env()
    model = recording_model(ModelGateway).openai(settings.openai_model, settings.fallback_model)
    async with Client(build_server(store, embedder)) as client:
        tools = ToolGateway(
            {"rag": client},
            timeout_seconds=settings.tool_timeout_seconds,
            max_chars=settings.tool_result_max_chars,
            max_same_calls=settings.limits.max_same_tool_calls,
        )
        # ToolGateway는 도구 목록을 처음 부를 때 채우므로, 여러 시나리오가 동시에 빈 목록을 보지 않게 미리 한 번 읽는다.
        from app.graph.nodes import CONSTRAINT_TOOLS

        await tools.specs(CONSTRAINT_TOOLS)
        deps = SimpleNamespace(settings=settings, model=model, tools=tools)
        gate = asyncio.Semaphore(args.concurrency)
        done = 0

        async def guarded(scenario: Scenario) -> dict:
            nonlocal done
            async with gate:
                try:
                    result = await run_scenario(scenario, deps)
                except Exception as error:  # 한 시나리오 실패로 전체 측정을 버리지 않는다.
                    result = {"scenario": scenario.to_dict(), "error": repr(error)}
                done += 1
                print(
                    f"[{done}/{len(scenarios)}] {scenario.id} {'오류 ' + result['error'] if 'error' in result else ''}",
                    flush=True,
                )
                return result

        results = await asyncio.gather(*(guarded(s) for s in scenarios))

    by_id = {s.id: s for s in scenarios}
    ok = [r for r in results if "error" not in r]
    scored = [r | {"id": r["scenario"]["id"], "per_cat": score(r, table, by_id[r["scenario"]["id"]])} for r in ok]
    summary = summarize(scored) | {"errors": [r for r in results if "error" in r]}
    corpus_info = {"documents": len(documents), "chunks": len(table), "embedding_model": embedder.model}

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"constraint_citation_{args.label}.json").write_text(
        json.dumps({"corpus": corpus_info, "summary": summary, "results": scored}, ensure_ascii=False, indent=1, default=list),
        encoding="utf-8",
    )
    (OUTPUT_DIR / f"constraint_citation_{args.label}.md").write_text(
        render_markdown(args.label, args, corpus_info, summary, wrong_examples(scored, table)), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, ensure_ascii=False, indent=1))
    print(f"오류 시나리오 {len(summary['errors'])}개")


if __name__ == "__main__":
    asyncio.run(main())
