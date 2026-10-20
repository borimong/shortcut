"""문서 색인 CLI.

    python -m rag_mcp.indexer --docs ../../data/docs --out ./index
    EMBEDDING_PROVIDER=openai OPENAI_API_KEY=... python -m rag_mcp.indexer --docs ... --out ...

색인을 다시 만들 때는 rag-mcp 서버를 재시작한다. 서버와 색인기는 같은 EMBEDDING_PROVIDER를 써야 한다.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .chunker import load_dir
from .embedder import get_embedder
from .store import LocalVectorStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="data/docs/*.md를 조항·씬 단위로 잘라 색인한다")
    ap.add_argument("--docs", default="../../data/docs")
    ap.add_argument("--out", default="./index")
    args = ap.parse_args(argv)

    chunks = load_dir(args.docs)
    embedder = get_embedder()
    store = LocalVectorStore.build(chunks, embedder)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    store.save(out)

    print(f"색인 완료: {store.meta['docCount']}개 문서, {store.meta['chunkCount']}개 chunk")
    print(f"Embedding: {store.meta['embeddingModel']} ({store.meta['dim']}차원) → {out}/meta.json에 기록")
    for doc_id in store.doc_ids():
        print(f"  - {doc_id}: {', '.join(store.sections(doc_id))}")


if __name__ == "__main__":
    main()
