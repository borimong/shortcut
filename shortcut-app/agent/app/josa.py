"""앞말 받침에 맞는 조사를 붙입니다. 백엔드 Josa, 프론트 format.js의 josa와 같은 규칙입니다.

한글은 마지막 글자의 받침으로, 숫자와 영문은 읽는 소리(v1 일, v2 이, L 엘)로 가릅니다. 끝이 괄호면 괄호 앞말을 봅니다.
"""

from __future__ import annotations

import re

# 받침이 있을 때 쓰는 조사와 없을 때 쓰는 조사다.
PAIRS = {"은": "는", "이": "가", "을": "를", "과": "와", "으로": "로"}
UNITS = ("km", "mm", "cm", "kg", "mg", "ml")


def _ending(word: str) -> str:
    """'none'(받침 없음), 'rieul'(ㄹ 받침), 'other'(그 밖의 받침) 가운데 하나입니다."""
    text = re.sub(r"\([^()]*\)$", "", str(word).strip()).strip()
    if not text:
        return "none"
    last = text[-1]
    if "가" <= last <= "힣":
        jong = (ord(last) - ord("가")) % 28
        return "none" if jong == 0 else "rieul" if jong == 8 else "other"
    if last.isdigit():
        digits = re.search(r"[0-9,]+$", text).group(0).replace(",", "")
        if digits.endswith("0"):
            return "other"  # 영, 십, 백, 천, 만
        return "rieul" if last in "178" else "other" if last in "36" else "none"
    if last.isascii() and last.isalpha():
        if text.lower().endswith(UNITS):
            return "none"
        return "rieul" if last.upper() in "LR" else "other" if last.upper() in "MN" else "none"
    return "none"


def josa(word: str, pair: str) -> str:
    """pair는 받침이 있을 때 쓰는 쪽('은', '이', '을', '과', '으로')으로 줍니다."""
    ending = _ending(word)
    batchim = ending == "other" if pair == "으로" else ending != "none"
    return f"{word}{pair if batchim else PAIRS[pair]}"
