"""환경 변수에서 Agent 서버 설정과 Harness 한도를 읽습니다."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Limits:
    """Agent Loop의 멈춤 조건입니다. 값을 바꾸면 Harness 명세와 평가표에 함께 남긴다."""

    # 한 번의 변경 이벤트에서 최적안을 다시 만드는 횟수 상한이다. 거절을 네 번까지 보완하고 다섯 번째 거절 뒤에는 사람이 조건을 정리한다.
    max_loops: int = 5
    # 도구 호출 총량 상한이다. 대본 범주와 후보 장소별 허가, 비행금지 검색이 들어간 뒤(PR #8) 실측은 첫 루프 41회,
    # 거절 뒤 루프는 근거 수집만 20회를 넘었다(2026-10-26). 거절 두 번과 4안 구성까지 약 100회라 120으로 잡았다.
    max_tool_calls: int = 120
    # 루프 하나의 자동 탐색 시간 상한(초)이다. 승인 대기는 빼고, 거절로 새 루프가 시작되면 다시 센다.
    # 현장에서 재계획 한 번을 기다릴 수 있는 시간으로 2분을 잡았다.
    max_seconds: int = 120
    # 같은 도구를 같은 인자로 부르는 횟수 상한이다. 세 번 같은 결과를 받고도 반복하면 모델이 막힌 것으로 본다.
    max_same_tool_calls: int = 3
    # LLM이 도구를 고르는 노드 하나의 내부 반복 상한이다.
    max_node_tool_rounds: int = 6
    # 자체 검토 통과 점수(100점 만점)다. 승인자가 추가 질문 없이 판단할 수 있는 수준을 80점으로 본다.
    review_pass_score: int = 80
    # 자체 검토 반복 상한이다. 다섯 번 고쳐도 80점에 못 미치면 가장 점수가 높았던 안으로 승인을 요청한다.
    max_review_rounds: int = 5
    # 실행팀 supervisor의 판단 횟수 상한이다. 3단계와 단계마다 재지시 1회, 수정 요청 재실행을 더해도 8회면 충분하다.
    max_exec_rounds: int = 8
    # 실행 Agent 하나의 도구 선택 반복 상한이다. 장소는 확인, 가예약, 확정, 이전 예약 취소로 4회가 필요하다.
    max_exec_tool_rounds: int = 6


@dataclass(frozen=True)
class Settings:
    """서비스 주소, 모델, Harness 값을 한곳에 모읍니다."""

    backend_url: str
    internal_token: str
    business_mcp_url: str
    rag_mcp_url: str
    ops_mcp_url: str
    rabbitmq_url: str
    checkpoint_dsn: str
    openai_model: str
    fallback_model: str
    limits: Limits
    tool_timeout_seconds: float
    tool_result_max_chars: int
    context_token_budget: int
    langsmith_project: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            backend_url=os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8080"),
            internal_token=os.getenv("INTERNAL_TOKEN", "local-internal-token"),
            business_mcp_url=os.getenv("BUSINESS_MCP_URL", "http://localhost:9101/mcp"),
            rag_mcp_url=os.getenv("RAG_MCP_URL", "http://localhost:9102/mcp"),
            ops_mcp_url=os.getenv("OPS_MCP_URL", "http://localhost:9103/mcp"),
            rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
            # checkpointer 테이블을 업무 테이블과 섞지 않으려고 agent 스키마를 search_path로 지정한다.
            checkpoint_dsn=os.getenv(
                "CHECKPOINT_DSN", "postgresql://shortcut:shortcut@localhost:5432/shortcut?options=-csearch_path%3Dagent"
            ),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            fallback_model=os.getenv("FALLBACK_MODEL", "gpt-4.1-mini"),
            limits=Limits(
                max_loops=_int("MAX_LOOPS", 5),
                max_tool_calls=_int("MAX_TOOL_CALLS", 120),
                max_seconds=_int("MAX_SECONDS", 120),
                max_same_tool_calls=_int("MAX_SAME_TOOL_CALLS", 3),
                review_pass_score=_int("REVIEW_PASS_SCORE", 80),
                max_review_rounds=_int("MAX_REVIEW_ROUNDS", 5),
                max_exec_rounds=_int("MAX_EXEC_ROUNDS", 8),
                max_exec_tool_rounds=_int("MAX_EXEC_TOOL_ROUNDS", 6),
            ),
            tool_timeout_seconds=float(os.getenv("TOOL_TIMEOUT_SECONDS", "15")),
            # 도구 결과를 그대로 넘기면 27개 후보 평가 결과만으로 수천 토큰이 되므로 4000자에서 자른다.
            tool_result_max_chars=_int("TOOL_RESULT_MAX_CHARS", 4000),
            # gpt-4o-mini 문맥 창보다 훨씬 작게 잡아 비용과 지연을 제한한다.
            context_token_budget=_int("CONTEXT_TOKEN_BUDGET", 6000),
            langsmith_project=os.getenv("LANGSMITH_PROJECT"),
        )
