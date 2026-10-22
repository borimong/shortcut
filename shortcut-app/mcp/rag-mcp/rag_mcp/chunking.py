"""규정과 계약서 문서를 조항 단위 chunk로 나눈다.

chunk 원문은 반드시 문서 원문의 부분 문자열이어야 한다. Agent가 근거를 인용하기 전에
`rag://documents/{doc_id}` 원문 안에 chunk 원문이 그대로 있는지 확인하기 때문이다.
"""
from __future__ import annotations

from dataclasses import dataclass

# 조항 하나가 이 길이를 넘으면 문단 단위로 다시 나눈다.
# 근거 패널에 그대로 보여 줄 수 있고 임베딩 한 번에 의미가 섞이지 않는 크기다.
MAX_CHUNK_CHARS = 800


@dataclass(frozen=True)
class Document:
    """색인 대상 문서 한 건."""

    doc_id: str
    title: str
    doc_type: str  # LAW, PERMIT, NO_FLY, SAFETY, POLICY, CONTRACT, SCRIPT
    version: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """검색 단위가 되는 조항 조각. chunk_id = '{doc_id}#{번호}'."""

    chunk_id: str
    doc_id: str
    chunk_no: int
    heading: str
    text: str


def parse_markdown(raw: str) -> Document:
    """머리말(---로 감싼 key: value)과 본문으로 된 코퍼스 파일을 읽는다."""
    lines = raw.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("문서 머리말(---)이 없다")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("문서 머리말이 닫히지 않았다")
    meta = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    missing = [k for k in ("doc_id", "title", "doc_type", "version") if not meta.get(k)]
    if missing:
        raise ValueError(f"머리말에 {', '.join(missing)}가 없다")
    body = "\n".join(lines[end + 1 :]).strip()
    return Document(meta["doc_id"], meta["title"], meta["doc_type"], meta["version"], body)


def split_into_chunks(document: Document) -> list[Chunk]:
    """'## ' 제목을 조항 경계로 보고 자른다. 첫 제목 앞의 머리글도 '개요' 조각으로 남긴다."""
    sections: list[tuple[str, list[str]]] = [("개요", [])]
    for line in document.text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for heading, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        for piece in _split_long(body):
            chunk_no = len(chunks)
            chunks.append(Chunk(f"{document.doc_id}#{chunk_no}", document.doc_id, chunk_no, heading, piece))
    return chunks


def _split_long(body: str) -> list[str]:
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    pieces, current = [], ""
    for paragraph in body.split("\n"):
        if current and len(current) + len(paragraph) + 1 > MAX_CHUNK_CHARS:
            pieces.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces
