"""코퍼스 문서를 rag-mcp의 index_document 도구로 색인하는 오프라인 작업입니다.

질문과 별개로 미리 색인해 두고, 이미 같은 버전이 색인된 문서는 건너뜁니다.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastmcp import Client

from rag_mcp.chunking import parse_markdown

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


async def index_corpus(client: Client, corpus_dir: Path = CORPUS_DIR) -> list[dict]:
    """버전이 바뀌었거나 아직 없는 문서만 색인하고 결과 목록을 돌려줍니다."""
    info = json.loads((await client.read_resource("rag://index/info"))[0].text)
    indexed = {d["doc_id"]: d["version"] for d in info["documents"]}
    results = []
    for path in sorted(corpus_dir.glob("*.md")):
        document = parse_markdown(path.read_text(encoding="utf-8"))
        if indexed.get(document.doc_id) == document.version:
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
