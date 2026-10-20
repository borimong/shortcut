"""prompts/*.md에 버전 관리되는 Instructions를 읽어 채웁니다."""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


@cache
def _load(name: str) -> tuple[str, str]:
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    # 파일 내용의 해시를 버전으로 쓰면 trace와 평가 결과에서 어떤 프롬프트로 돌린 결과인지 구분할 수 있다.
    return text, hashlib.sha256(text.encode()).hexdigest()[:8]


def render(name: str, **values: object) -> str:
    """$이름 자리표시자를 채웁니다. 프롬프트 안의 JSON 중괄호와 겹치지 않게 Template을 쓴다."""
    text, _ = _load(name)
    return Template(text).substitute({key: str(value) for key, value in values.items()})


def prompt_versions() -> dict[str, str]:
    """모든 프롬프트 파일의 버전을 돌려줍니다."""
    return {path.stem: _load(path.stem)[1] for path in sorted(PROMPT_DIR.glob("*.md"))}
