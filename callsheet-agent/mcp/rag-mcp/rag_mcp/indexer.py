"""코퍼스 문서를 rag-mcp의 index_document 도구로 색인하는 오프라인 작업.

질문과 별개로 미리 색인해 둔다. 같은 버전이 같은 임베딩 모델로 이미 색인된 문서는 건너뛰고,
버전이나 임베딩 모델이 바뀐 문서만 다시 색인한다.

실행:  RAG_MCP_URL=http://localhost:9102/mcp python -m rag_mcp.indexer
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastmcp import Client

from rag_mcp.chunking import parse_markdown

CORPUS_DIR = Path(os.getenv("RAG_CORPUS_DIR", Path(__file__).resolve().parent.parent / "corpus"))


async def index_corpus(client: Client, corpus_dir: Path = CORPUS_DIR) -> list[dict]:
    """버전이나 임베딩 모델이 바뀌었거나 아직 없는 문서만 색인하고 결과 목록을 돌려준다."""
    info = json.loads((await client.read_resource("rag://index/info"))[0].text)
    model = info["embedding_model"]
    indexed = {d["doc_id"]: (d["version"], d.get("embedding_model")) for d in info["documents"]}
    results = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        document = parse_markdown(path.read_text(encoding="utf-8"))
        if indexed.get(document.doc_id) == (document.version, model):
            results.append({"doc_id": document.doc_id, "skipped": True})
            continue
        result = await client.call_tool(
            "index_document",
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "doc_type": document.doc_type,
                "version": document.version,
                "text": document.text,
            },
        )
        results.append(result.data)
    return results


async def main() -> None:
    url = os.getenv("RAG_MCP_URL", "http://localhost:9102/mcp")
    async with Client(url) as client:
        for row in await index_corpus(client):
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
