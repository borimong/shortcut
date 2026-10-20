"""rag-mcp 테스트. data/docs의 가상 문서를 hash Embedding으로 임시 색인해 쓴다 (외부 호출 없음).

    cd mcp/rag-mcp && pytest -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from rag_mcp.chunker import chunk_markdown, load_dir
from rag_mcp.embedder import HashEmbedder
from rag_mcp.retriever import Retriever
from rag_mcp.server import create_server
from rag_mcp.store import IndexMismatchError, LocalVectorStore

DOCS = Path(__file__).resolve().parents[3] / "data" / "docs"


def make_retriever(tmp: Path | None = None) -> Retriever:
    emb = HashEmbedder(512)
    store = LocalVectorStore.build(load_dir(DOCS), emb)
    if tmp:
        store.save(tmp)
        store = LocalVectorStore.load(tmp, emb)
    return Retriever(store, emb)


def data(result):
    sc = getattr(result, "structured_content", None)
    if sc is None:  # 구조화 결과가 없으면 텍스트(JSON)를 읽는다
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


# ---------------------------------------------------------------- chunker / store


def test_chunker_sections_and_scene_ids():
    chunks = load_dir(DOCS)
    keys = {(c.docId, c.section) for c in chunks}
    assert ("contract-A03", "5.2") in keys and ("permit-seoul", "2.3") in keys
    s21 = next(c for c in chunks if c.section == "S21")
    assert s21.meta["sceneId"] == "S21" and s21.meta["type"] == "script"


def test_chunker_requires_front_matter():
    with pytest.raises(ValueError, match="메타데이터"):
        chunk_markdown("## 1.1 제목\n본문")


def test_index_records_model_and_rejects_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        make_retriever(Path(tmp))
        meta = json.loads((Path(tmp) / "meta.json").read_text(encoding="utf-8"))
        assert meta["embeddingModel"] == "hash-ngram-512" and meta["dim"] == 512
        with pytest.raises(IndexMismatchError):
            LocalVectorStore.load(tmp, HashEmbedder(256))


def test_search_finds_work_hours_clause():
    hits = make_retriever().search("하루 촬영 시간 한도", k=3, where={"type": "contract", "actorId": "A03"})
    assert hits[0]["docId"] == "contract-A03" and hits[0]["section"] == "5.2"


# ---------------------------------------------------------------- MCP


@pytest.mark.anyio
async def test_tools_are_read_only():
    async with Client(create_server(make_retriever())) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == {"search_permit_rules", "search_contract_terms", "search_script"}
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


@pytest.mark.anyio
async def test_contract_and_permit_search():
    async with Client(create_server(make_retriever())) as client:
        terms = data(await client.call_tool("search_contract_terms", {"actor_id": "A03", "query": "휴식시간", "k": 2}))
        rules = data(await client.call_tool("search_permit_rules", {"query": "허가 시간대", "region": "서울 중구"}))
    assert terms[0]["section"] == "5.3"
    assert rules[0]["docId"] == "permit-seoul" and rules[0]["section"] == "2.3"
    assert {"docId", "section", "title", "snippet", "score"} <= set(terms[0])


@pytest.mark.anyio
async def test_unknown_inputs_return_retry_info():
    async with Client(create_server(make_retriever())) as client:
        with pytest.raises(ToolError) as e1:
            await client.call_tool("search_permit_rules", {"query": "허가", "region": "부산"})
        with pytest.raises(ToolError) as e2:
            await client.call_tool("search_contract_terms", {"actor_id": "A99", "query": "근로시간"})
    assert "서울 중구" in str(e1.value)
    assert "A03" in str(e2.value)


@pytest.mark.anyio
async def test_script_and_resource():
    async with Client(create_server(make_retriever())) as client:
        hits = data(await client.call_tool("search_script", {"scene_id": "S21"}))
        contents = await client.read_resource(f"doc://{hits[0]['docId']}/{hits[0]['section']}")
        clause = await client.read_resource("doc://contract-A03/5.2")
        index = json.loads((await client.read_resource("doc://index"))[0].text)
    assert "(야외, 낮)" in contents[0].text
    assert "최대 12시간" in clause[0].text
    assert index["embeddingModel"] == "hash-ngram-512"
