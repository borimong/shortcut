"""규정과 계약서 문서를 조항 단위 chunk로 나눕니다."""

from __future__ import annotations

from dataclasses import dataclass

# 조항 하나가 이 길이를 넘으면 문단 단위로 다시 나눈다.
# 근거 패널에 그대로 보여 줄 수 있고 임베딩 한 번에 의미가 섞이지 않는 크기로 800자를 잡았다.
MAX_CHUNK_CHARS = 800


@dataclass(frozen=True)
class Document:
    """색인 대상 문서 한 건입니다."""

    doc_id: str
    title: str
    doc_type: str
    version: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """검색 단위가 되는 조항 조각입니다."""

    chunk_id: str
    doc_id: str
    chunk_no: int
    heading: str
    text: str


def parse_markdown(raw: str) -> Document:
    """머리말(---로 감싼 key: value)과 본문으로 된 코퍼스 파일을 읽습니다."""
    lines = raw.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("문서 머리말이 없습니다")
    end = lines.index("---", 1)
    meta = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    body = "\n".join(lines[end + 1 :]).strip()
    return Document(meta["doc_id"], meta["title"], meta["doc_type"], meta["version"], body)


def split_into_chunks(document: Document) -> list[Chunk]:
    """'## ' 제목을 조항 경계로 보고 자릅니다. 제목 앞의 머리글도 한 조각으로 남깁니다."""
    sections: list[tuple[str, list[str]]] = [("개요", [])]
    for line in document.text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)

    chunks = []
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
