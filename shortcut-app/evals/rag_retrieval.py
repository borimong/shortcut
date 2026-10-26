"""rag-mcp 검색 품질을 정답셋(evals/rag_golden.json)으로 잽니다. 생성은 빼고 검색만 봅니다.

두 가지를 같은 정답셋으로 돌립니다.
  live      지금 떠 있는 rag-mcp(pgvector + text-embedding-3-small)에 MCP로 search_regulation, search_contract_clause를 호출
  variants  같은 코퍼스를 메모리에 다시 색인해 임베딩 모델, 제목 붙이기, BM25, 하이브리드를 바꿔 가며 비교

코퍼스가 작아서(규정 22조각) 상위 4개 안에 있는지만 보면 거의 다 맞습니다.
그래서 1등 적중(Hit@1), 정답 순위(MRR), 헷갈리는 질의, 답 없는 질의의 점수를 함께 봅니다.

rag_mcp 패키지와 fastmcp가 rag-mcp 이미지에 있으므로 그 이미지로 compose 네트워크에 붙여 실행합니다(떠 있는 컨테이너는 건드리지 않음).
  OPENAI_API_KEY=... docker run --rm --network shortcut_default -e OPENAI_API_KEY \\
    -v "$PWD":/work -w /work -e PYTHONPATH=/app:/work shortcut-rag-mcp \\
    python -m evals.rag_retrieval --label baseline
  옵션: --check(정답셋 chunk_id만 확인), --no-live, --no-variants, --url http://rag-mcp:9102/mcp
결과: outputs/rag_retrieval_{label}.json, .md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_mcp.chunking import Chunk, Document, parse_markdown, split_into_chunks
# 운영 rag-mcp의 하이브리드 검색과 같은 BM25를 쓴다.
from rag_mcp.lexical import Bm25

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "rag_golden.json"
CORPUS_DIR = ROOT / "mcp" / "rag-mcp" / "corpus"
OUTPUT_DIR = ROOT / "outputs"

REGULATION_TYPES = ["LAW", "PERMIT", "NO_FLY", "SAFETY", "POLICY"]
# 도구가 허용하는 최대 k로 받아서 순위를 매긴다. Agent의 기본 k는 4다.
REGULATION_K = 8
CONTRACT_K = 5
DEFAULT_K = 4


@dataclass
class Result:
    """질의 하나를 검색한 결과."""

    qid: str
    category: str
    query: str
    relevant: list[str]
    returned: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    latency_ms: float | None = None

    @property
    def rank(self) -> int | None:
        for i, row in enumerate(self.returned, 1):
            if row["chunk_id"] in self.relevant:
                return i
        return None

    @property
    def top1_score(self) -> float | None:
        return self.returned[0]["score"] if self.returned else None


# ---------- 정답셋과 코퍼스 ----------


def load_golden() -> list[dict[str, Any]]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["queries"]


def load_corpus() -> tuple[dict[str, Document], list[Chunk]]:
    documents, chunks = {}, []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        document = parse_markdown(path.read_text(encoding="utf-8"))
        documents[document.doc_id] = document
        chunks.extend(split_into_chunks(document))
    return documents, chunks


def check_golden(queries: list[dict[str, Any]], documents: dict[str, Document], chunks: list[Chunk]) -> list[str]:
    """정답셋의 chunk_id가 지금 코퍼스에 실제로 있는지 본다. 코퍼스를 고치면 번호가 밀릴 수 있다."""
    known = {c.chunk_id for c in chunks}
    problems = []
    for q in queries:
        for cid in q["relevant"]:
            if cid not in known:
                problems.append(f"{q['id']}: {cid} 조각이 코퍼스에 없음")
        if q["category"] == "contract" and not q.get("expect_error") and q["contract_doc_id"] not in documents:
            problems.append(f"{q['id']}: {q['contract_doc_id']} 계약서가 코퍼스에 없음")
        for cid in q["relevant"]:
            doc_type = documents.get(cid.split("#")[0])
            if q["category"] != "contract" and doc_type and doc_type.doc_type == "CONTRACT":
                problems.append(f"{q['id']}: 규정 검색 정답에 계약서 조각 {cid}")
    return problems


# ---------- live: 떠 있는 rag-mcp ----------


def _rows(result: Any) -> list[dict[str, Any]]:
    """fastmcp 버전에 따라 리스트 반환값이 structured_content['result'] 또는 본문 JSON으로 온다."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and isinstance(structured.get("result"), list):
        return structured["result"]
    if isinstance(getattr(result, "data", None), list) and all(isinstance(r, dict) for r in result.data):
        return result.data
    return json.loads(result.content[0].text)


async def run_live(url: str, queries: list[dict[str, Any]]) -> tuple[list[Result], dict[str, Any]]:
    from fastmcp import Client

    results = []
    async with Client(url) as client:
        info = json.loads((await client.read_resource("rag://index/info"))[0].text)
        for q in queries:
            if q["category"] == "contract":
                name, args = (
                    "search_contract_clause",
                    {"query": q["query"], "contract_doc_id": q["contract_doc_id"], "k": CONTRACT_K},
                )
            else:
                name, args = "search_regulation", {"query": q["query"], "k": REGULATION_K}
                if q.get("doc_types"):
                    args["doc_types"] = q["doc_types"]
            row = Result(q["id"], q["category"], q["query"], q["relevant"])
            started = time.perf_counter()
            response = await client.call_tool(name, args, raise_on_error=False)
            row.latency_ms = round((time.perf_counter() - started) * 1000, 1)
            if response.is_error:
                text = response.content[0].text if response.content else ""
                code = re.search(r"\[([A-Z_]+)\]", text)
                row.error = code.group(1) if code else text[:120]
            else:
                row.returned = [
                    {"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "doc_type": r["doc_type"], "score": r["score"]}
                    for r in _rows(response)
                ]
            results.append(row)
    return results, info


# ---------- variants: 메모리에 다시 색인해 비교 ----------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def chunk_text(chunk: Chunk, documents: dict[str, Document], with_title: bool) -> str:
    # rag-mcp index_document와 같은 형식(제목, 조항 제목, 본문)이 기본이다.
    return f"{documents[chunk.doc_id].title}\n{chunk.heading}\n{chunk.text}" if with_title else chunk.text


def candidates(q: dict[str, Any], documents: dict[str, Document], chunks: list[Chunk]) -> tuple[list[Chunk], int] | str:
    """도구와 같은 범위로 후보를 거른다. 없는 계약서면 서버처럼 오류 코드를 돌려준다."""
    if q["category"] == "contract":
        if q["contract_doc_id"] not in documents:
            return "CONTRACT_NOT_FOUND"
        return [c for c in chunks if c.doc_id == q["contract_doc_id"]], CONTRACT_K
    types = q.get("doc_types") or REGULATION_TYPES
    return [c for c in chunks if documents[c.doc_id].doc_type in types], REGULATION_K


def rank_with(
    scores_for: Any, queries: list[dict[str, Any]], documents: dict[str, Document], chunks: list[Chunk]
) -> list[Result]:
    results = []
    for i, q in enumerate(queries):
        row = Result(q["id"], q["category"], q["query"], q["relevant"])
        scope = candidates(q, documents, chunks)
        if isinstance(scope, str):
            row.error = scope
        else:
            pool, k = scope
            scored = sorted(((scores_for(i, c), c) for c in pool), key=lambda x: x[0], reverse=True)[:k]
            row.returned = [
                {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "doc_type": documents[c.doc_id].doc_type, "score": round(s, 4)}
                for s, c in scored
            ]
        results.append(row)
    return results


def run_variants(queries: list[dict[str, Any]], documents: dict[str, Document], chunks: list[Chunk]) -> dict[str, list[Result]]:
    from rag_mcp.embedding import HashEmbedder, OpenAIEmbedder

    texts = [q["query"] for q in queries]
    runs: dict[str, list[Result]] = {}
    dense: dict[str, tuple[list[list[float]], dict[str, list[float]]]] = {}

    def add_dense(name: str, embedder: Any, with_title: bool) -> None:
        try:
            q_vecs = embedder.embed(texts)
            c_vecs = dict(
                zip(
                    [c.chunk_id for c in chunks],
                    embedder.embed([chunk_text(c, documents, with_title) for c in chunks]),
                    strict=True,
                )
            )
        except Exception as error:  # 키 권한에 없는 모델은 건너뛴다.
            print(f"[skip] {name}: {error}")
            return
        dense[name] = (q_vecs, c_vecs)
        runs[name] = rank_with(lambda i, c: _cosine(q_vecs[i], c_vecs[c.chunk_id]), queries, documents, chunks)

    add_dense("hash-256 (개발용)", HashEmbedder(256), True)
    add_dense("3-small, 제목 붙임 (운영 설정)", OpenAIEmbedder("text-embedding-3-small", 1536), True)
    add_dense("3-small, 본문만", OpenAIEmbedder("text-embedding-3-small", 1536), False)
    add_dense("3-large, 제목 붙임", OpenAIEmbedder("text-embedding-3-large", 3072), True)

    bm25 = Bm25({c.chunk_id: chunk_text(c, documents, True) for c in chunks})
    runs["BM25 (글자 2개 단위)"] = rank_with(lambda i, c: bm25.score(texts[i], c.chunk_id), queries, documents, chunks)

    base = "3-small, 제목 붙임 (운영 설정)"
    if base in dense:
        # 하이브리드: 의미 검색과 BM25의 순위를 RRF(1/(60+순위))로 합친다. 점수 크기가 달라도 합칠 수 있다.
        q_vecs, c_vecs = dense[base]
        fused = []
        for i, q in enumerate(queries):
            scope = candidates(q, documents, chunks)
            if isinstance(scope, str):
                fused.append({})
                continue
            pool, _ = scope
            by_dense = sorted(pool, key=lambda c: _cosine(q_vecs[i], c_vecs[c.chunk_id]), reverse=True)
            by_bm25 = sorted(pool, key=lambda c: bm25.score(texts[i], c.chunk_id), reverse=True)
            rrf = Counter()
            for order in (by_dense, by_bm25):
                for r, c in enumerate(order, 1):
                    rrf[c.chunk_id] += 1 / (60 + r)
            fused.append(rrf)
        runs["하이브리드 RRF (3-small + BM25)"] = rank_with(
            lambda i, c: fused[i].get(c.chunk_id, 0.0), queries, documents, chunks
        )
    return runs


# ---------- 지표 ----------


def violations(r: Result, q: dict[str, Any]) -> list[str]:
    """도구가 지켜야 할 범위를 벗어난 결과. 규정 검색에 계약서, doc_types 밖 문서, 다른 계약서가 섞이면 위반이다."""
    bad = []
    for row in r.returned:
        if q["category"] == "contract":
            if row["doc_id"] != q["contract_doc_id"]:
                bad.append(row["chunk_id"])
        elif row["doc_type"] not in (q.get("doc_types") or REGULATION_TYPES):
            bad.append(row["chunk_id"])
    return bad


def summarize(results: list[Result], queries: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {q["id"]: q for q in queries}
    positives = [r for r in results if r.relevant]
    ranks = [r.rank for r in positives]

    def hit(k: int, rows: list[Result]) -> float:
        return round(sum(1 for r in rows if r.rank and r.rank <= k) / len(rows), 3) if rows else 0.0

    def mrr(rows: list[Result]) -> float:
        return round(sum(1 / r.rank for r in rows if r.rank) / len(rows), 3) if rows else 0.0

    per_category = {}
    for category in dict.fromkeys(q["category"] for q in queries):
        rows = [r for r in positives if r.category == category]
        if rows:
            per_category[category] = {"n": len(rows), "hit1": hit(1, rows), "hit4": hit(DEFAULT_K, rows), "mrr": mrr(rows)}

    negatives = [r for r in results if r.category == "negative"]
    correct_top1 = sorted(r.top1_score for r in positives if r.rank == 1 and r.top1_score is not None)
    negative_top1 = sorted(r.top1_score for r in negatives if r.top1_score is not None)
    expected_errors = [r for r in results if by_id[r.qid].get("expect_error")]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    return {
        "n_positive": len(positives),
        "hit1": hit(1, positives),
        "hit3": hit(3, positives),
        "hit4": hit(DEFAULT_K, positives),
        "mrr": mrr(positives),
        "misses_at_k": sum(1 for x in ranks if x is None),
        "per_category": per_category,
        "violations": {r.qid: violations(r, by_id[r.qid]) for r in results if violations(r, by_id[r.qid])},
        "unexpected_errors": {r.qid: r.error for r in results if r.error and not by_id[r.qid].get("expect_error")},
        "expected_errors_ok": f"{sum(1 for r in expected_errors if r.error == by_id[r.qid]['expect_error'])}/{len(expected_errors)}",
        "correct_top1_scores": correct_top1,
        "negative_top1_scores": negative_top1,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1),
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 1),
        }
        if latencies
        else None,
    }


def threshold_table(summary: dict[str, Any]) -> list[tuple[float, float, float]]:
    """점수 기준선 t를 두면 맞는 1등 결과는 얼마나 남고, 답 없는 질의는 얼마나 걸러지는가."""
    pos, neg = summary["correct_top1_scores"], summary["negative_top1_scores"]
    if not pos or not neg:
        return []
    rows = []
    for t in sorted({round(x, 2) for x in (*pos, *neg)} | {round(min(pos) - 0.01, 2)}):
        keep = sum(1 for x in pos if x >= t) / len(pos)
        drop = sum(1 for x in neg if x < t) / len(neg)
        rows.append((t, round(keep, 3), round(drop, 3)))
    return rows


# ---------- 보고서 ----------


def fmt_returned(r: Result, n: int = 3) -> str:
    return ", ".join(f"{x['chunk_id']}({x['score']})" for x in r.returned[:n]) or (r.error or "없음")


def to_markdown(
    label: str, live: dict[str, Any] | None, variants: dict[str, dict[str, Any]], detail: list[Result] | None, info: dict | None
) -> str:
    lines = [f"# RAG 검색 평가: {label}", ""]
    lines += [
        "정답셋 `evals/rag_golden.json` 기준. 규정 검색은 k=8, 계약서 검색은 k=5로 받아 순위를 매겼다(Agent 기본 k=4).",
        "Hit@1은 1등이 정답인 비율, Hit@4는 Agent가 실제로 받는 4개 안에 정답이 있는 비율, MRR은 정답 순위의 역수 평균이다.",
        "",
    ]
    if info:
        docs = info.get("documents", [])
        lines += [
            f"- 떠 있는 색인: 임베딩 {info.get('embedding_model')} ({info.get('dimension')}차원), 문서 {len(docs)}건, 조각 {sum(d.get('chunks', 0) for d in docs)}개",
            "",
        ]

    table = ([("live (떠 있는 rag-mcp)", live)] if live else []) + list(variants.items())
    lines += [
        "## 전체 지표",
        "",
        "| 구성 | Hit@1 | Hit@3 | Hit@4 | MRR | k 안에 정답 없음 | 범위 위반 | 오류 거부 | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in table:
        lat = s["latency_ms"] or {}
        lines.append(
            f"| {name} | {s['hit1']} | {s['hit3']} | {s['hit4']} | {s['mrr']} | {s['misses_at_k']}/{s['n_positive']} | "
            f"{len(s['violations'])} | {s['expected_errors_ok']} | {lat.get('p50', '-')} | {lat.get('p95', '-')} |"
        )

    categories = list(table[0][1]["per_category"]) if table else []
    lines += [
        "",
        "## 질의 유형별 Hit@1",
        "",
        "| 구성 | " + " | ".join(f"{c} (n={table[0][1]['per_category'][c]['n']})" for c in categories) + " |",
    ]
    lines.append("|---|" + "---|" * len(categories))
    for name, s in table:
        lines.append(f"| {name} | " + " | ".join(str(s["per_category"][c]["hit1"]) for c in categories) + " |")

    lines += ["", "## 답 없는 질의와 점수 기준선", ""]
    for name, s in table:
        if "BM25" in name or "RRF" in name or "hash" in name:
            continue
        pos, neg = s["correct_top1_scores"], s["negative_top1_scores"]
        if not pos or not neg:
            continue
        lines.append(
            f"- {name}: 맞힌 1등 점수 {min(pos)}~{max(pos)} (중앙값 {round(statistics.median(pos), 3)}), "
            f"답 없는 질의의 1등 점수 {min(neg)}~{max(neg)} (중앙값 {round(statistics.median(neg), 3)})"
        )
        best = max(threshold_table(s), key=lambda row: (min(row[1], row[2]), row[1]))
        lines.append(
            f"  - 가장 균형 잡힌 기준선 {best[0]}: 맞는 결과 {best[1] * 100:.0f}% 유지, 답 없는 질의 {best[2] * 100:.0f}% 걸러냄"
        )

    if detail:
        misses = [r for r in detail if r.relevant and r.rank != 1]
        lines += [
            "",
            f"## live에서 1등을 놓친 질의 ({len(misses)}건)",
            "",
            "| id | 유형 | 질의 | 정답 | 정답 순위 | 실제 상위 3개 |",
            "|---|---|---|---|---|---|",
        ]
        for r in misses:
            lines.append(
                f"| {r.qid} | {r.category} | {r.query} | {', '.join(r.relevant)} | {r.rank or '없음'} | {fmt_returned(r)} |"
            )
        lines += ["", "## live에서 답 없는 질의의 결과", "", "| id | 질의 | 상위 3개 |", "|---|---|---|"]
        for r in detail:
            if r.category == "negative":
                lines.append(f"| {r.qid} | {r.query} | {fmt_returned(r)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--url", default="http://rag-mcp:9102/mcp")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--no-variants", action="store_true")
    args = parser.parse_args()

    queries = load_golden()
    documents, chunks = load_corpus()
    problems = check_golden(queries, documents, chunks)
    print(f"정답셋 {len(queries)}개, 코퍼스 문서 {len(documents)}건, 조각 {len(chunks)}개, 문제 {len(problems)}건")
    for p in problems:
        print(" -", p)
    if problems or args.check:
        raise SystemExit(1 if problems else 0)

    live_results, info, live_summary = None, None, None
    if not args.no_live:
        live_results, info = asyncio.run(run_live(args.url, queries))
        live_summary = summarize(live_results, queries)
    variant_summaries = {}
    variant_results = {}
    if not args.no_variants:
        variant_results = run_variants(queries, documents, chunks)
        variant_summaries = {name: summarize(rs, queries) for name, rs in variant_results.items()}

    OUTPUT_DIR.mkdir(exist_ok=True)
    payload = {
        "label": args.label,
        "index_info": info,
        "live": {"summary": live_summary, "results": [r.__dict__ | {"rank": r.rank} for r in live_results or []]},
        "variants": {
            name: {"summary": variant_summaries[name], "results": [r.__dict__ | {"rank": r.rank} for r in rs]}
            for name, rs in variant_results.items()
        },
    }
    (OUTPUT_DIR / f"rag_retrieval_{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = to_markdown(args.label, live_summary, variant_summaries, live_results, info)
    (OUTPUT_DIR / f"rag_retrieval_{args.label}.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
