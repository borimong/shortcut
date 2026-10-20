"""그래프 실행 한 번에 필요한 의존성을 묶습니다. 체크포인트에는 저장되지 않습니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.harness.model import ModelGateway
from app.harness.observability import EventPublisher
from app.harness.tools import ToolGateway


@dataclass
class RunContext:
    """LangGraph context_schema로 넘기는 실행 컨텍스트입니다."""

    task_id: str
    trace_id: str
    settings: Settings
    model: ModelGateway
    tools: ToolGateway
    events: EventPublisher
    store: Any = None
    # 노드 래퍼가 State의 카운터를 복사해 넣고 노드가 끝나면 다시 State에 씁니다.
    counter: dict[str, Any] = field(default_factory=dict)
