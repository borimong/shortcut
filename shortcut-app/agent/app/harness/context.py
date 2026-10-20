"""모델 입력을 Token 예산 안에 맞추고 오래된 루프 기록을 요약합니다."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from langchain_core.messages import BaseMessage, ToolMessage


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:
        # 토크나이저 파일을 받을 수 없는 환경에서도 예산 판단은 해야 하므로 근사치로 대신한다.
        return None


def count_tokens(text: str) -> int:
    """gpt-4o 계열 토크나이저 기준 토큰 수를 셉니다."""
    encoder = _encoder()
    if encoder is None:
        # 한국어는 대략 두 글자에 한 토큰이라 길이의 절반을 근사치로 쓴다.
        return max(1, len(text) // 2)
    return len(encoder.encode(text))


@dataclass(frozen=True)
class Section:
    """모델 입력의 한 덩어리입니다. priority가 작을수록 끝까지 남긴다."""

    title: str
    text: str
    priority: int


def fit_sections(sections: list[Section], budget: int) -> str:
    """예산을 넘으면 우선순위가 낮은 덩어리부터 줄이거나 뺍니다."""
    kept = {section.title: section.text for section in sections}
    dropped = "(Token 예산 초과로 생략)"
    for section in sorted(sections, key=lambda s: s.priority, reverse=True):
        # 덜 중요한 덩어리를 예산에 맞을 때까지 먼저 줄여야 중요한 덩어리가 자르기 오차 때문에 잘리지 않는다.
        while _total(sections, kept) > budget and kept[section.title] != dropped:
            overflow = _total(sections, kept) - budget
            current = kept[section.title]
            remaining_tokens = count_tokens(current) - overflow
            if remaining_tokens <= 50:
                kept[section.title] = dropped
            else:
                # 토큰과 글자 수 비율이 고르다고 보고 남길 비율보다 10퍼센트 더 잘라 반복 횟수를 줄인다.
                keep_chars = int(len(current) * remaining_tokens / count_tokens(current) * 0.9)
                kept[section.title] = current[:keep_chars] + "\n(Token 예산 초과로 이하 생략)"
        if _total(sections, kept) <= budget:
            break
    return "\n\n".join(f"## {s.title}\n{kept[s.title]}" for s in sections)


def _total(sections: list[Section], kept: dict[str, str]) -> int:
    return sum(count_tokens(f"## {s.title}\n{kept[s.title]}") for s in sections)


def summarize_loops(summaries: list[str], keep_last: int = 1) -> str:
    """최근 루프만 그대로 두고 그 전 루프는 거절 사유와 제외 조건만 남긴 한 줄로 줄입니다."""
    if len(summaries) <= keep_last:
        return "\n".join(summaries) or "이전 루프 없음"
    older = summaries[:-keep_last]
    compact = "; ".join(line.split(" | 결과: ")[-1] for line in older)
    return f"이전 {len(older)}개 루프 요약: {compact}\n" + "\n".join(summaries[-keep_last:])


def trim_messages(messages: list[BaseMessage], budget: int) -> list[BaseMessage]:
    """도구 반복 중 대화가 예산을 넘으면 가장 오래된 도구 결과부터 짧은 표시로 바꿉니다."""
    trimmed = list(messages)
    for index, message in enumerate(trimmed):
        if sum(count_tokens(str(m.content)) for m in trimmed) <= budget:
            break
        if isinstance(message, ToolMessage) and not str(message.content).startswith("(이전 도구 결과"):
            trimmed[index] = ToolMessage(
                content=f"(이전 도구 결과 생략: {message.name}, {len(str(message.content))}자)",
                tool_call_id=message.tool_call_id,
                name=message.name,
            )
    return trimmed
