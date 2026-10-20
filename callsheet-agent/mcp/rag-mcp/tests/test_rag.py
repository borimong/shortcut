"""rag-mcp 테스트 (계약 rc2). data/docs의 가상 문서를 hash Embedding으로 임시 색인해 쓴다 (외부 호출 없음).

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
    if sc is None:
        return json.loads(result.content[0].text)
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


# ---------------------------------------------------------------- chunker / store


def test_chunker_reads_versions_and_categories():
    chunks = load_dir(DOCS)
    keys = {(c.docId, c.section) for c in chunks}
    assert ("law-labor", "53") in keys and ("contract-A04-v3", "5.4") in keys and ("zone-paju", "2.1") in keys
    v2 = next(c for c in chunks if c.docId == "contract-A04-v2")
    assert v2.meta["status"] == "SUPERSEDED" and v2.meta["supersededBy"] == "contract-A04-v3"


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


# ---------------------------------------------------------------- MCP


@pytest.mark.anyio
async def test_tools_are_read_only():
    async with Client(create_server(make_retriever())) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == {"search_regulation", "search_contract_clause", "get_source"}
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


@pytest.mark.anyio
async def test_regulation_search_by_category():
    async with Client(create_server(make_retriever())) as client:
        law = data(await client.call_tool("search_regulation", {"query": "1주 최대 근로시간 52시간", "category": "LABOR_LAW", "k": 1}))
        rain = data(await client.call_tool("search_regulation", {"query": "강수 확률 높은 시간대 야외 촬영", "category": "FILMING_PERMIT", "k": 1}))
        drone = data(await client.call_tool("search_regulation", {"query": "드론 비행", "category": "NO_FILMING_ZONE", "k": 1}))
    assert (law[0]["docId"], law[0]["section"]) == ("law-labor", "53")
    assert (rain[0]["docId"], rain[0]["section"]) == ("permit-hangang", "3.1")
    assert (drone[0]["docId"], drone[0]["section"]) == ("zone-paju", "2.1")


@pytest.mark.anyio
async def test_contract_search_is_scoped_to_current_version():
    async with Client(create_server(make_retriever())) as client:
        hits = data(await client.call_tool("search_contract_clause", {"contract_doc_id": "contract-A04-v3", "query": "야간 촬영 몇 시 이후", "k": 1}))
        with pytest.raises(ToolError) as old:
            await client.call_tool("search_contract_clause", {"contract_doc_id": "contract-A04-v2", "query": "야간"})
        with pytest.raises(ToolError) as none:
            await client.call_tool("search_contract_clause", {"contract_doc_id": "contract-A99-v1", "query": "야간"})
    assert hits[0]["docId"] == "contract-A04-v3" and hits[0]["section"] == "5.4"
    assert "[SUPERSEDED]" in str(old.value) and "contract-A04-v3" in str(old.value)
    assert "[NO_DOCS]" in str(none.value) and "contract-A01-v3" in str(none.value)


@pytest.mark.anyio
async def test_get_source_and_resources():
    async with Client(create_server(make_retriever())) as client:
        src = data(await client.call_tool("get_source", {"doc_id": "contract-A04-v3", "section": "5.4"}))
        res = await client.read_resource("doc://law-labor/54")
        index = json.loads((await client.read_resource("doc://index"))[0].text)
        with pytest.raises(ToolError) as e:
            await client.call_tool("get_source", {"doc_id": "law-labor", "section": "99"})
    assert "22:00 이후" in src["text"]
    assert "30분 이상" in res[0].text
    assert index["embeddingModel"] == "hash-ngram-512" and any(d["status"] == "SUPERSEDED" for d in index["docs"])
    assert "53" in str(e.value)
