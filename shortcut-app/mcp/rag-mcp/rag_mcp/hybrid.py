"""의미 검색(벡터) 결과에 BM25 키워드 순위를 섞는 하이브리드 순위.

왜: 검색 평가(evals/results/phase1_rag_retrieval.md)에서 벡터만 쓰면 "야간근로 가산 수당",
"22시 이후 촬영 제한"처럼 숫자·법률 용어 질의와 구어체 질의에서 1등을 놓쳤다(Hit@1 0.778).
같은 코퍼스로 BM25를 RRF로 섞으면 Hit@1 0.841, Hit@4 0.952였다(오프라인 비교).

방법:
1. 도구와 같은 범위(문서 종류, 계약서 한 건)로 벡터 검색 결과를 넉넉히(pool) 받는다.
2. 같은 후보를 BM25로 다시 매긴다. 한국어는 형태소 분석기 없이 어절 안의 글자 두 개씩을 토큰으로 쓴다.
3. 두 순위를 RRF(1/(60+순위))로 합쳐 상위 k개를 돌려준다. 점수 크기가 달라도 순위만으로 합칠 수 있다.

후보 거르기(범위)는 벡터 검색이 이미 했으므로 BM25가 범위 밖 문서를 끌어올 수 없다.
돌려주는 score는 기존과 같은 코사인 유사도다(순서만 바뀐다).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

RRF_K = 60
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def bigrams(text: str) -> list[str]:
    """어절 안의 글자 두 개씩. 한 글자 어절은 그대로 쓴다. 조사가 붙어도 앞부분이 겹치게 된다."""
    tokens: list[str] = []
    for word in _TOKEN.findall(text.lower()):
        tokens.extend([word] if len(word) == 1 else [word[i : i + 2] for i in range(len(word) - 1)])
    return tokens


class Bm25:
    """후보 몇십 개에 쓰는 작은 BM25. 색인을 따로 두지 않고 질의마다 후보로 만든다."""

    def __init__(self, texts: dict[str, str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = {key: Counter(bigrams(text)) for key, text in texts.items()}
        self.lengths = {key: sum(counts.values()) for key, counts in self.docs.items()}
        self.avg = (sum(self.lengths.values()) / len(self.lengths)) if self.lengths else 0.0
        df = Counter(term for counts in self.docs.values() for term in counts)
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}
        self.k1, self.b = k1, b

    def score(self, query: str, key: str) -> float:
        counts, length = self.docs[key], self.lengths[key]
        if not self.avg:
            return 0.0
        total = 0.0
        for term in set(bigrams(query)):
            tf = counts.get(term, 0)
            if tf:
                norm = self.k1 * (1 - self.b + self.b * length / self.avg)
                total += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
        return total


def row_text(row: dict[str, Any]) -> str:
    """색인할 때 임베딩한 것과 같은 형식(문서 제목, 조항 제목, 본문)."""
    return f"{row.get('title', '')}\n{row.get('heading', '')}\n{row.get('text', '')}"


def fuse(query: str, rows: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """벡터 순서로 온 rows를 BM25 순위와 RRF로 합쳐 상위 k개를 돌려준다."""
    if not rows:
        return []
    keys = [row["chunk_id"] for row in rows]
    bm25 = Bm25({row["chunk_id"]: row_text(row) for row in rows})
    by_keyword = sorted(keys, key=lambda key: bm25.score(query, key), reverse=True)
    fused: Counter[str] = Counter()
    for order in (keys, by_keyword):
        for rank, key in enumerate(order, 1):
            fused[key] += 1 / (RRF_K + rank)
    position = {key: i for i, key in enumerate(keys)}
    # 동점이면 벡터 순서를 따른다.
    ranked = sorted(rows, key=lambda row: (-fused[row["chunk_id"]], position[row["chunk_id"]]))
    return ranked[:k]
