"""rag-mcp의 청킹, 검색 범위, 오류 처리, 색인 작업을 네트워크 없이 검증합니다."""

from __future__ import annotations

import asyncio
import hashlib
import math

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from rag_mcp.chunking import parse_markdown, split_into_chunks
from rag_mcp.indexer import CORPUS_DIR, index_corpus
from rag_mcp.server import build_server


class HashEmbedder:
    """단어 해시를 세는 결정적 임베딩입니다. 실제 모델 없이 검색 순서를 재현하려고 쓴다."""

    model = "hash-test"
    dimension = 64

    def __init__(self, fail: bool = False):
        self.fail = fail

    def embed(self, texts):
        if self.fail:
            raise RuntimeError("rate limited")
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in text.replace("\n", " ").split():
                vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimension] += 1.0
            vectors.append(vector)
        return vectors


class MemoryStore:
    """PgVectorStore와 같은 메서드를 가진 메모리 저장소입니다."""

    def __init__(self):
        self.documents, self.chunks = {}, {}

    def upsert(self, document, chunks, vectors, model):
        self.delete(document.doc_id)
        self.documents[document.doc_id] = {
            "doc_id": document.doc_id,
            "title": document.title,
            "doc_type": document.doc_type,
            "version": document.version,
            "text": document.text,
            "embedding_model": model,
            "embedding_dim": len(vectors[0]),
        }
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.chunks[chunk.chunk_id] = (chunk, vector)

    def delete(self, doc_id):
        existed = self.documents.pop(doc_id, None) is not None
        self.chunks = {k: v for k, v in self.chunks.items() if v[0].doc_id != doc_id}
        return existed

    def search(self, vector, k, *, doc_types=None, doc_id=None):
        rows = []
        for chunk, stored in self.chunks.values():
            document = self.documents[chunk.doc_id]
            if doc_types and document["doc_type"] not in doc_types:
                continue
            if doc_id and chunk.doc_id != doc_id:
                continue
            rows.append(
                {
                    **document,
                    "chunk_id": chunk.chunk_id,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "score": _cosine(vector, stored),
                }
            )
        return sorted(rows, key=lambda row: row["score"], reverse=True)[:k]

    def get_document(self, doc_id):
        return self.documents.get(doc_id)

    def list_documents(self):
        return [
            {**d, "chunks": sum(1 for c, _ in self.chunks.values() if c.doc_id == d["doc_id"])} for d in self.documents.values()
        ]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def indexed_server():
    store = MemoryStore()
    server = build_server(store, HashEmbedder())

    async def setup():
        async with Client(server) as client:
            await index_corpus(client)

    run(setup())
    return server, store


def test_markdown_is_split_by_article_heading():
    document = parse_markdown((CORPUS_DIR / "law-labor-standards.md").read_text(encoding="utf-8"))
    chunks = split_into_chunks(document)
    headings = [c.heading for c in chunks]
    assert document.doc_type == "LAW"
    assert "제53조 연장 근로의 제한" in headings
    assert chunks[0].chunk_id == "law-labor-standards#0"


def test_regulation_search_never_returns_contracts(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            return (await client.call_tool("search_regulation", {"query": "야간 촬영 22시 이후", "k": 8})).data

    hits = run(scenario())
    assert hits
    assert all(hit["doc_type"] != "CONTRACT" for hit in hits)


def test_contract_search_is_scoped_to_one_document(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            return (
                await client.call_tool(
                    "search_contract_clause",
                    {"query": "22시 이후의 촬영은 하지 않는다", "contract_doc_id": "contract-actor-a-v3"},
                )
            ).data

    hits = run(scenario())
    assert {hit["doc_id"] for hit in hits} == {"contract-actor-a-v3"}
    assert hits[0]["heading"] == "제6조 야간 촬영"


def test_unknown_contract_lists_available_ids(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("search_contract_clause", {"query": "야간", "contract_doc_id": "contract-actor-z-v1"})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "[CONTRACT_NOT_FOUND]" in str(error.value)
    assert "contract-actor-a-v3" in str(error.value)


def test_embedding_failure_is_retryable():
    server = build_server(MemoryStore(), HashEmbedder(fail=True))

    async def scenario():
        async with Client(server) as client:
            await client.call_tool("search_regulation", {"query": "주 52시간"})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "retryable=true" in str(error.value)


def test_resource_returns_full_original_text(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            return (await client.read_resource("rag://documents/contract-actor-a-v3"))[0].text

    text = run(scenario())
    assert "제11조 위약" in text


def test_indexer_skips_documents_with_same_version(indexed_server):
    server, store = indexed_server

    async def scenario():
        async with Client(server) as client:
            return await index_corpus(client)

    results = run(scenario())
    assert all(row.get("skipped") for row in results)
    assert len(store.documents) == len(list(CORPUS_DIR.glob("*.md")))


def test_delete_is_destructive_and_reports_missing(indexed_server):
    server, _ = indexed_server

    async def scenario():
        async with Client(server) as client:
            tools = {t.name: t for t in await client.list_tools()}
            assert tools["delete_document"].annotations.destructive_hint is True
            await client.call_tool("delete_document", {"doc_id": "budget-approval-policy"})
            await client.call_tool("delete_document", {"doc_id": "budget-approval-policy"})

    with pytest.raises(ToolError) as error:
        run(scenario())
    assert "[DOCUMENT_NOT_FOUND]" in str(error.value)
