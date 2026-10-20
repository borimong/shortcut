"""검색 로직. MCP와 무관한 순수 함수라 단위 테스트가 쉽다.

모든 검색 결과는 같은 형식으로 돌려준다 (아키텍처 문서 4장 sources[], 7장 rag-mcp):
    {docId, section, title, snippet, score}
docId + section으로 doc://{docId}/{section} Resource를 읽으면 원문이 나온다.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .chunker import Chunk, load_dir
from .embedder import Embedder, get_embedder
from .store import LocalVectorStore

log = logging.getLogger("rag_mcp")
SNIPPET_CHARS = 180


def to_hit(c: Chunk, score: float | None = None) -> dict:
    snippet = " ".join(c.text.split())
    if len(snippet) > SNIPPET_CHARS:
        snippet = snippet[:SNIPPET_CHARS] + "…"
    hit = {"docId": c.docId, "section": c.section, "title": f"{c.title} {c.sectionTitle}", "snippet": snippet}
    if score is not None:
        hit["score"] = round(score, 4)
    return hit


class Retriever:
    def __init__(self, store: LocalVectorStore, embedder: Embedder):
        self.store = store
        self.embedder = embedder

    def search(self, query: str, k: int = 5, where: dict | None = None) -> list[dict]:
        qv = self.embedder.embed([query])[0]
        return [to_hit(c, s) for c, s in self.store.search(qv, k=k, where=where)]

    def scene(self, scene_id: str) -> list[dict]:
        return [to_hit(c) for c in self.store.filter({"type": "script", "sceneId": scene_id})]

    def section_text(self, doc_id: str, section: str) -> Chunk | None:
        return self.store.get(doc_id, section)


def open_retriever(index_dir: str | None = None, docs_dir: str | None = None, embedder: Embedder | None = None) -> Retriever:
    """색인이 있으면 불러오고, 없으면 docs_dir 문서로 새로 만든다."""
    index_dir = index_dir or os.environ.get("RAG_INDEX_DIR", "./index")
    docs_dir = docs_dir or os.environ.get("RAG_DOCS_DIR", "../../data/docs")
    embedder = embedder or get_embedder()
    if LocalVectorStore.exists(index_dir):
        store = LocalVectorStore.load(index_dir, embedder)
        log.info("색인 불러옴: %s (%s, %d chunks)", index_dir, store.meta["embeddingModel"], store.meta["chunkCount"])
    else:
        store = LocalVectorStore.build(load_dir(Path(docs_dir)), embedder)
        store.save(index_dir)
        log.info("색인 새로 만듦: %s → %s (%d chunks)", docs_dir, index_dir, len(store.chunks))
    return Retriever(store, embedder)
