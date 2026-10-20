"""Markdown 문서를 조항(또는 씬) 단위 chunk로 자른다.

문서 형식 (C와 합의, data/docs/*.md):

    ---
    docId: contract-A04-v3
    type: contract            # contract | regulation
    category: CONTRACT        # regulation이면 LABOR_LAW | CONTRACT_LAW | FILMING_PERMIT | NO_FILMING_ZONE
    title: 출연 계약서 v3 (A04 차여름)
    actorId: A04              # 선택: contract
    version: 3                # 선택: contract
    status: CURRENT           # 선택: CURRENT | SUPERSEDED
    supersededBy: ...         # 선택: SUPERSEDED일 때 새 버전 docId
    ---
    ## 5.2 근로시간
    본문 ...

`## ` 제목 하나가 chunk 하나다. 제목의 첫 단어(5.2, 53)가 section ID가 되어
Resource 주소 doc://{docId}/{section}과 위반 스키마 source.section에 쓰인다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SECTION_ID = re.compile(r"^(S\d+|\d+(?:\.\d+)*)\b")


@dataclass
class Chunk:
    docId: str
    section: str
    title: str          # 문서 제목
    sectionTitle: str   # 조항 제목
    text: str
    meta: dict = field(default_factory=dict)  # type, actorId, region, sceneId

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        raise ValueError("문서 맨 위에 --- 로 감싼 메타데이터(docId, type, title)가 필요하다")
    _, head, body = raw.split("---", 2)
    meta = {}
    for line in head.strip().splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    for key in ("docId", "type", "title"):
        if key not in meta:
            raise ValueError(f"메타데이터에 {key}가 없다")
    return meta, body


def _slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-")[:40] or "section"


def chunk_markdown(raw: str) -> list[Chunk]:
    meta, body = _parse_front_matter(raw)
    chunks: list[Chunk] = []
    current_title, lines = None, []

    def flush() -> None:
        if current_title is None:
            return
        text = "\n".join(lines).strip()
        if not text:
            return
        m = _SECTION_ID.match(current_title)
        section = m.group(1) if m else _slug(current_title)
        extra = {k: v for k, v in meta.items() if k not in ("docId", "title")}
        if section.startswith("S") and meta["type"] == "script":
            extra["sceneId"] = section
        chunks.append(Chunk(meta["docId"], section, meta["title"], current_title, text, extra))

    for line in body.splitlines():
        if line.startswith("## "):
            flush()
            current_title, lines = line[3:].strip(), []
        elif current_title is not None:
            lines.append(line)
    flush()

    seen: set[str] = set()
    for c in chunks:
        if c.section in seen:
            raise ValueError(f"{meta['docId']}에 section {c.section}이 두 번 나온다")
        seen.add(c.section)
    return chunks


def load_dir(docs_dir: str | Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8")))
    if not chunks:
        raise FileNotFoundError(f"{docs_dir}에 색인할 .md 문서가 없다")
    return chunks
