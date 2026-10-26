"""하이브리드 검색(벡터 + BM25 순위 합치기)을 네트워크 없이 검증한다."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client

from rag_mcp.embedding import HashEmbedder
from rag_mcp.hybrid import bigrams, fuse
from rag_mcp.indexer import index_corpus
from rag_mcp.server import build_server
from rag_mcp.store import MemoryStore


def run(coro):
    return asyncio.run(coro)


def data(result):
    if getattr(result, "data", None) is not None:
        return result.data
    return json.loads(result.content[0].text)


def indexed(mode):
    server = build_server(MemoryStore(), HashEmbedder(64), search_mode=mode)

    async def setup():
        async with Client(server) as client:
            await index_corpus(client)

    run(setup())
    return server


def call(server, name, args):
    async def scenario():
        async with Client(server) as client:
            return data(await client.call_tool(name, args))

    return run(scenario())


def row(chunk_id, text, heading=""):
    return {"chunk_id": chunk_id, "title": "문서", "heading": heading, "text": text, "score": 0.5}


def test_bigrams_split_korean_words_into_two_letter_tokens():
    assert bigrams("야간근로") == ["야간", "간근", "근로"]
    assert bigrams("22시 이후") == ["22", "2시", "이후"]
    assert bigrams("밤 A") == ["밤", "a"]


def test_fuse_lifts_keyword_match_over_vector_only_hit():
    # 벡터로는 2등이지만 질의 단어를 그대로 가진 조각이, 벡터 1등이지만 단어가 하나도 안 겹치는 조각을 앞선다.
    rows = [
        row("a", "기상 악화 시 촬영 중단"),
        row("c", "연장근로와 야간근로에 대하여는 통상임금의 100분의 50 이상을 가산", "제56조 연장, 야간 및 휴일 근로"),
        row("b", "근로시간은 휴게시간을 제외하고 40시간"),
    ]
    assert [r["chunk_id"] for r in fuse("야간근로 가산 수당", rows, k=3)] == ["c", "a", "b"]


def test_fuse_keeps_vector_order_when_no_keyword_overlaps_and_respects_k():
    rows = [row("a", "기상 악화"), row("b", "드론 비행"), row("c", "예산 상한")]
    assert [r["chunk_id"] for r in fuse("전혀 무관한 질의어", rows, k=3)] == ["a", "b", "c"]
    assert len(fuse("드론", rows, k=1)) == 1
    assert fuse("아무거나", [], k=3) == []


def test_hybrid_regulation_search_stays_in_scope():
    hits = call(indexed("hybrid"), "search_regulation", {"query": "야간근로 가산 수당", "k": 8})
    assert len(hits) == 8
    assert all(hit["doc_type"] not in {"CONTRACT", "SCRIPT"} for hit in hits)
    narrowed = call(indexed("hybrid"), "search_regulation", {"query": "드론 비행", "k": 8, "doc_types": ["NO_FLY"]})
    assert narrowed and {hit["doc_type"] for hit in narrowed} == {"NO_FLY"}


def test_hybrid_keeps_contract_scope():
    hits = call(indexed("hybrid"), "search_contract_clause",
                {"query": "22시 이후의 촬영", "contract_doc_id": "contract-actor-a-v3", "k": 5})
    assert hits and {hit["doc_id"] for hit in hits} == {"contract-actor-a-v3"}
    assert hits[0]["heading"] == "제6조 야간 촬영"


def test_vector_mode_is_still_available_and_reported():
    server = indexed("vector")

    async def info():
        async with Client(server) as client:
            return json.loads((await client.read_resource("rag://index/info"))[0].text)

    assert run(info())["search_mode"] == "vector"
    hits = call(server, "search_regulation", {"query": "주 52시간 연장 근로 한도", "k": 3})
    assert len(hits) == 3


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        build_server(MemoryStore(), HashEmbedder(64), search_mode="bm25-only")
