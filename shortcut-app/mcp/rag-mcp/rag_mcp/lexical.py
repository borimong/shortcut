"""BM25 키워드 검색과 RRF 순위 합치기.

의미 검색(임베딩)은 바꿔 말한 질의에 강하고, BM25는 조항 번호, 장소 이름, 금액처럼 글자가 그대로 겹치는 질의에 강하다.
두 순위를 RRF로 합치면 점수 크기가 달라도 섞을 수 있다. evals/rag_retrieval.py가 같은 코퍼스로 잰
"하이브리드 RRF (3-small + BM25)" 구성이 이 모듈이다.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence

# RRF에서 순위에 더하는 상수. 원 논문 값이며, 1등과 2등의 차이가 지나치게 벌어지지 않게 한다.
RRF_K = 60


def bigrams(text: str) -> list[str]:
    """한국어는 형태소 분석기 없이 어절 안의 글자 두 개씩을 토큰으로 쓴다(조사가 붙어도 겹치게)."""
    tokens = []
    for word in re.findall(r"[0-9A-Za-z가-힣]+", text.lower()):
        tokens.extend([word] if len(word) == 1 else [word[i : i + 2] for i in range(len(word) - 1)])
    return tokens


class Bm25:
    """chunk_id -> 본문으로 만든 BM25 색인. IDF는 넘겨받은 전체 조각 기준이다."""

    def __init__(self, texts: dict[str, str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = {cid: Counter(bigrams(t)) for cid, t in texts.items()}
        self.lengths = {cid: sum(c.values()) for cid, c in self.docs.items()}
        self.avg = sum(self.lengths.values()) / len(self.lengths) if self.lengths else 0.0
        df = Counter(term for counts in self.docs.values() for term in counts)
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}
        self.k1, self.b = k1, b

    def score(self, query: str, cid: str) -> float:
        counts, length = self.docs.get(cid), self.lengths.get(cid, 0)
        if not counts or not self.avg:
            return 0.0
        total = 0.0
        for term in set(bigrams(query)):
            tf = counts.get(term, 0)
            if tf:
                total += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
        return total


def rrf(rankings: Iterable[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """순위 목록 여러 개를 1/(k+순위)의 합으로 합친다. 순위는 1부터 센다."""
    fused: Counter[str] = Counter()
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            fused[cid] += 1 / (k + rank)
    return dict(fused)
