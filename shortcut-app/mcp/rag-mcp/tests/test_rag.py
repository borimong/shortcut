"""rag-mcp의 청킹, 검색 범위, 오류 처리, Resource, 색인 작업을 네트워크 없이 검증한다."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from rag_mcp.chunking import parse_markdown, split_into_chunks
from rag_mcp.embedding import HashEmbedder
from rag_mcp.indexer import CORPUS_DIR, index_corpus
from rag_mcp.server import build_server
from rag_mcp.store import MemoryStore

# shortcut-app/agent가 부르는 도구 (접두어 rag_ 제외)
AGENT_TOOLS = {"search_regulation", "search_contract_clause", "search_script", "index_document", "delete_document"}


class FailingEmbedder(HashEmbedder):
    def embed(self, texts):
        raise RuntimeError("rate limited")


def run(coro):
    return asyncio.run(coro)


def data(result):
    if getattr(result, "data", None) is not None:
        return result.data
    return json.loads(result.content[0].text)


def make_indexed(embedder=None):
    store = MemoryStore()
    server = build_server(store, embedder or HashEmbedder(64))

    async def setup():
        async with Client(server) as client:
            await index_corpus(client)

    run(setup())
    return server, store


@pytest.fixture()
def indexed_server():
    return make_indexed()


def tool_call(server, name, args):
    async def scenario():
        async with Client(server) as client:
            return await client.call_tool(name, args)

    return run(scenario())


def test_markdown_is_split_by_article_heading_and_chunks_are_substrings():
    document = parse_markdown((CORPUS_DIR / "law-labor-standards.md").read_text(encoding="utf-8"))
    chunks = split_into_chunks(document)
    assert document.doc_type == "LAW"
    assert "제53조 연장 근로의 제한" in [c.heading for c in chunks]
    assert chunks[0].chunk_id == "law-labor-standards#0"
    # Agent는 chunk 원문이 문서 원문 안에 그대로 있는지 확인한 뒤에만 근거로 인용한다.
    assert all(c.text in document.text for c in chunks)


def test_tools_match_agent_and_resources_exist(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}
            info = json.loads((await client.read_resource("rag://index/info"))[0].text)
            return tools, info

    tools, info = run(scenario())
    assert set(tools) == AGENT_TOOLS
    assert tools["search_regulation"].annotations.read_only_hint is True
    assert tools["delete_document"].annotations.destructive_hint is True
    assert info["embedding_model"] == "hash-64"
    assert len(info["documents"]) == len(list(CORPUS_DIR.glob("*.md")))


def test_regulation_search_never_returns_contracts(indexed_server):
    server, _ = indexed_server
    hits = data(tool_call(server, "search_regulation", {"query": "야간 촬영 22시 이후", "k": 8}))
    assert hits
    assert all(hit["doc_type"] not in ("CONTRACT", "SCRIPT") for hit in hits)
    assert {"chunk_id", "doc_id", "title", "heading", "text", "score"} <= set(hits[0])


def test_regulation_search_can_narrow_doc_types(indexed_server):
    server, _ = indexed_server
    hits = data(tool_call(server, "search_regulation", {"query": "드론 비행", "doc_types": ["NO_FLY"]}))
    assert hits and {hit["doc_type"] for hit in hits} == {"NO_FLY"}


def test_contract_search_is_scoped_to_one_document(indexed_server):
    server, _ = indexed_server
    hits = data(tool_call(server, "search_contract_clause",
                          {"query": "22시 이후의 촬영은 하지 않는다", "contract_doc_id": "contract-actor-a-v3"}))
    assert {hit["doc_id"] for hit in hits} == {"contract-actor-a-v3"}
    assert hits[0]["heading"] == "제6조 야간 촬영"


def test_unknown_contract_lists_available_ids(indexed_server):
    server, _ = indexed_server
    with pytest.raises(ToolError) as error:
        tool_call(server, "search_contract_clause", {"query": "야간", "contract_doc_id": "contract-actor-z-v1"})
    assert "[CONTRACT_NOT_FOUND]" in str(error.value)
    assert "contract-actor-a-v3" in str(error.value)
    assert "retryable=false" in str(error.value)


def test_embedding_failure_is_retryable():
    server = build_server(MemoryStore(), FailingEmbedder(64))
    with pytest.raises(ToolError) as error:
        tool_call(server, "search_regulation", {"query": "주 52시간"})
    assert "[EMBEDDING_UNAVAILABLE]" in str(error.value)
    assert "retryable=true" in str(error.value)


def test_resource_returns_full_original_text_containing_hits(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            hits = data(await client.call_tool(
                "search_contract_clause", {"query": "위약", "contract_doc_id": "contract-actor-a-v3"}))
            text = (await client.read_resource("rag://documents/contract-actor-a-v3"))[0].text
            return hits, text

    hits, text = run(scenario())
    assert "제11조 위약" in text
    assert all(hit["text"] in text for hit in hits)


def test_indexer_skips_same_version_and_reindexes_when_model_changes(indexed_server):
    server, store = indexed_server

    async def again(srv):
        async with Client(srv) as client:
            return await index_corpus(client)

    assert all(row.get("skipped") for row in run(again(server)))
    # 같은 저장소를 다른 임베딩 모델로 띄우면 모든 문서를 다시 색인한다.
    other = build_server(store, HashEmbedder(32))
    results = run(again(other))
    assert not any(row.get("skipped") for row in results)
    assert {d["embedding_model"] for d in store.list_documents()} == {"hash-32"}


def test_delete_is_destructive_and_reports_missing(indexed_server):
    server, _ = indexed_server
    assert data(tool_call(server, "delete_document", {"doc_id": "budget-approval-policy"}))["deleted"] is True
    with pytest.raises(ToolError) as error:
        tool_call(server, "delete_document", {"doc_id": "budget-approval-policy"})
    assert "[DOCUMENT_NOT_FOUND]" in str(error.value)


def test_script_is_split_by_scene_heading():
    document = parse_markdown((CORPUS_DIR / "script-ep07-v1.md").read_text(encoding="utf-8"))
    headings = [c.heading for c in split_into_chunks(document)]
    assert document.doc_type == "SCRIPT"
    assert "S#12. 한강 공원 산책로 (낮, 실외)" in headings
    assert "S#21. 합정 루프탑 (밤, 실외)" in headings


def test_script_search_returns_requested_scenes_in_order(indexed_server):
    server, _ = indexed_server
    hits = data(tool_call(server, "search_script", {"query": "밤 장면", "scene_codes": ["S21", "S12"]}))
    assert [hit["heading"] for hit in hits] == ["S#21. 합정 루프탑 (밤, 실외)", "S#12. 한강 공원 산책로 (낮, 실외)"]
    assert all(hit["doc_type"] == "SCRIPT" for hit in hits)
    free = data(tool_call(server, "search_script", {"query": "한강 산책", "k": 3}))
    assert len(free) == 3 and {hit["doc_type"] for hit in free} == {"SCRIPT"}


def test_place_scope_is_carried_from_front_matter_to_search_results(indexed_server):
    server, _ = indexed_server
    notice = split_into_chunks(parse_markdown((CORPUS_DIR / "no-fly-zone-notice.md").read_text(encoding="utf-8")))
    by_heading = {c.heading: c.locations for c in notice}
    # 문서 일부 조항만 특정 장소에 적용되고, 나머지 조항은 어디에나 적용된다.
    assert by_heading["휴전선 인근 비행금지구역"] == ("파주",)
    assert by_heading["비행 승인 원칙"] == ()

    hits = data(tool_call(server, "search_regulation", {"query": "한강 촬영 허가 시간", "k": 8, "doc_types": ["PERMIT"]}))
    # 허가서는 장소마다 하나씩 있고, 조각마다 자기 허가서 머리말의 장소가 붙는다.
    scope = {"permit-hangang-filming": ["한강"], "permit-hapjeong-rooftop": ["합정"]}
    assert hits and all(hit["locations"] == scope[hit["doc_id"]] for hit in hits)


def test_indexer_reindexes_when_place_scope_changes(indexed_server, tmp_path):
    server, store = indexed_server
    source = (CORPUS_DIR / "permit-hangang-filming.md").read_text(encoding="utf-8")
    changed = source.replace("locations: 한강", "locations: 한강, 여의도")
    (tmp_path / "permit-hangang-filming.md").write_text(changed, encoding="utf-8")

    async def again():
        async with Client(server) as client:
            return await index_corpus(client, tmp_path)

    assert not run(again())[0].get("skipped")
    hits = store.search([1.0] * 64, 50, doc_id="permit-hangang-filming")
    assert {tuple(hit["locations"]) for hit in hits} == {("한강", "여의도")}


def test_search_fuses_dense_and_bm25_ranks(indexed_server):
    server, _ = indexed_server
    hits = data(tool_call(server, "search_regulation", {"query": "주 52시간 연장 근로 한도", "k": 4}))
    assert hits and all(hit["retrieval"] == "hybrid" for hit in hits)
    # 순서는 RRF 점수로 정해지고, score에는 의미 검색의 코사인 유사도가 그대로 실린다.
    assert [hit["rank_score"] for hit in hits] == sorted((hit["rank_score"] for hit in hits), reverse=True)
    assert all(isinstance(hit["score"], float) for hit in hits)
    # 글자가 그대로 겹치는 법 조항은 개발용 해시 임베딩이 약해도 BM25 덕분에 1등으로 올라온다.
    assert hits[0]["doc_id"] == "law-labor-standards"


def test_embedding_failure_falls_back_to_bm25_within_scope(indexed_server):
    _, store = indexed_server
    server = build_server(store, FailingEmbedder(64))
    hits = data(tool_call(server, "search_regulation", {"query": "주 52시간 연장 근로 한도"}))
    assert hits and all(hit["retrieval"] == "lexical" and hit["score"] is None for hit in hits)
    assert hits[0]["doc_id"] == "law-labor-standards"
    assert all(hit["doc_type"] not in ("CONTRACT", "SCRIPT") for hit in hits)

    clauses = data(tool_call(server, "search_contract_clause",
                             {"query": "22시 이후의 촬영", "contract_doc_id": "contract-actor-a-v3"}))
    assert {hit["doc_id"] for hit in clauses} == {"contract-actor-a-v3"}


def test_embedding_failure_without_keyword_match_is_still_retryable(indexed_server):
    _, store = indexed_server
    server = build_server(store, FailingEmbedder(64))
    with pytest.raises(ToolError) as error:
        tool_call(server, "search_regulation", {"query": "qzxw"})
    assert "[EMBEDDING_UNAVAILABLE]" in str(error.value)


def test_bm25_index_follows_index_and_delete(indexed_server):
    server, _ = indexed_server
    text = "## 제1조 테스트\n흑요석 크레인은 풍속 초속 9미터를 넘으면 쓰지 않는다. 현장 안전 담당이 확인한다."
    args = {"doc_id": "policy-obsidian-crane", "title": "흑요석 크레인 운용 기준", "doc_type": "POLICY",
            "version": "v1", "text": text}
    tool_call(server, "search_regulation", {"query": "흑요석 크레인"})  # 새 문서를 넣기 전에 BM25 색인을 만들어 둔다.
    tool_call(server, "index_document", args)
    hits = data(tool_call(server, "search_regulation", {"query": "흑요석 크레인", "k": 1}))
    assert hits[0]["doc_id"] == "policy-obsidian-crane"

    tool_call(server, "delete_document", {"doc_id": "policy-obsidian-crane"})
    hits = data(tool_call(server, "search_regulation", {"query": "흑요석 크레인", "k": 8}))
    assert all(hit["doc_id"] != "policy-obsidian-crane" for hit in hits)
