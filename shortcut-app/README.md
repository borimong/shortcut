# ShortCut: 촬영 콜시트 재계획 AI Agent

촬영 변수(우천, 배우 일정, 장소 취소, 장비 고장, 천재지변) 하나가 틀어지면, 계약과 법규를 지키는 가장 좋은 대안 하나를 자동으로 다시 짜고, 필수 승인자 전원의 승인을 거쳐 웹에 공지하는 B2B 서비스입니다.

## 구성

| 서비스 | 기술 | 역할 | 공개 |
|---|---|---|---|
| frontend | Vue 3, Vite, Pinia, nginx | 오늘의 촬영판, 변경 입력, Agent 진행, 변경안 승인, 알림 | 8088 |
| backend | Spring Boot 3.5, Java 21 | 업무 API, JWT 인증, 제약/점수 엔진(업무 규칙 단일 위치), 작업 접수 202, SSE 중계, Outbox | 18080 |
| worker | backend와 같은 이미지(profile worker) | 콜시트 배포 큐 소비, 실패 재시도와 DLQ | 내부 |
| agent | FastAPI, LangGraph 1.2, LangChain 1.x | Harness로 감싼 재계획 그래프와 근거 질의응답 그래프 | 내부 |
| business-mcp | FastMCP 4.1 (`mcp/business-mcp`) | 업무 도구 14개(조회 10, 변경 4). DB 대신 backend `/internal/**` 호출 | 내부 |
| rag-mcp | FastMCP 4.1, pgvector (`mcp/rag-mcp`) | 규정 검색, 계약서 범위 검색, 색인과 삭제, 원문 Resource | 내부 |
| postgres | PostgreSQL 16 + pgvector | 업무 데이터(app), 임베딩(rag), checkpointer와 장기 메모리(agent) | 내부 |
| rabbitmq | RabbitMQ 3.13 | `agent.tasks`, `jobs.callsheet` 큐와 retry, DLQ | 관리 화면만 로컬 |

MCP 서버 2개의 코드는 `mcp/` 폴더에 있습니다(D 담당 안윤태 작성, 설명은 `mcp/README.md`).

```
화면 --REST/SSE--> backend --Outbox--> RabbitMQ(agent.tasks) --> agent --MCP(Streamable HTTP)--> business-mcp --> backend /internal/**
                      ^                                              |                          rag-mcp --> pgvector
                      +------------------ 진행 이벤트 ----------------+
```

## 실행 방법

1. `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`, `JWT_SECRET`, `INTERNAL_TOKEN`을 채웁니다. LangSmith trace를 보려면 `LANGSMITH_API_KEY`도 넣습니다.
2. 전체 서비스를 띄웁니다. 처음에는 이미지 빌드로 몇 분 걸립니다.
   ```bash
   docker compose up -d --build
   docker compose logs -f rag-indexer   # 규정 문서 8건 색인 확인 후 종료
   ```
3. 브라우저에서 http://localhost:8088 에 접속합니다. 데모 계정의 비밀번호는 모두 `shortcut1234`입니다.

| 계정 | 역할 | 할 수 있는 일 |
|---|---|---|
| manager | 제작실장 | 변경 입력 |
| director | 연출감독 | 변경 입력, 모든 변경안 승인 |
| ad1, ad2 | 1조감독, 2조감독 | 시간과 동선 변경 승인 |
| sound | 동시녹음팀장 | 장소 소음 관련 승인 |
| dop | 촬영감독 | 장비 변경 승인 |
| pd | 제작 PD | 추가 비용 승인 |
| crew | 연출부원 | 열람 |

시연 순서: manager로 로그인해 변경 입력에서 "우천"을 접수하면 Agent 진행 화면에서 노드와 도구 호출이 실시간으로 보입니다. 변경안 화면에서 sound로 로그인해 문제 요소(장소, 시간대, 장비, 비용, 기타)를 고르고 사유를 적어 거절하면, 진행 화면으로 이동해 고른 요소만 바꾼 다음 루프의 최적안 1개가 다시 올라옵니다. 1/2/3안이 모두 거절되면 세 안의 특징과 거절 사유에서 뽑은 키워드로 아워플레이스 대체 장소를 찾아 4안으로 다시 제안합니다. 필수 승인자가 모두 승인하면 콜시트가 확정되어 배포 알림이 갑니다.

## 테스트와 평가

```bash
# 단위 테스트 (네트워크, DB 없이)
cd agent && python -m pytest -q
cd mcp/business-mcp && python -m pytest -q   # MCP 서버 코드는 mcp/ 폴더에 있다 (설명은 mcp/README.md)
cd mcp/rag-mcp && python -m pytest -q
cd backend && mvn -q test

# 실제 서비스로 평가 시나리오 5개 실행 (compose 실행 중, .env의 INTERNAL_TOKEN과 같은 값을 넘긴다)
INTERNAL_TOKEN=... python -m evals.run_eval --label before
# 프롬프트, 한도, 모델 중 하나를 바꾼 뒤 다시 실행하고 비교표 생성
INTERNAL_TOKEN=... python -m evals.run_eval --label after
python -m evals.run_eval --compare before after
```

결과는 `outputs/eval_<label>.json`, `.md`, `outputs/eval_compare_<a>_<b>.md`에 저장됩니다.

## Harness 명세

| 요소 | 적용 위치 | 값 | 확인 테스트 |
|---|---|---|---|
| Instructions | `agent/prompts/*.md` | 역할, 하드 제약 7개, 도구 규칙, 금지 사항, 출력 형식. 파일 해시를 버전으로 trace에 기록 | `test_every_prompt_renders_and_has_a_version` |
| Tools | `agent/app/harness/tools.py` | 노드별 허용 목록, 결과 4000자 제한, 오류는 ToolMessage, 일시 오류 1회 재호출, 도구 타임아웃 15초 | `test_tool_not_in_allowlist...`, `test_tool_result_is_masked_truncated...` |
| Agent Loop | `agent/app/config.py`, `graph/builder.py` | 루프 5회, 도구 호출 60회(실측 첫 루프 16~20회에 재계획 루프마다 4~5회, 4안 구성 2회, 자체 검토의 후보 교체 검증), 자체 검토 80점 통과와 최대 5회, 루프마다 자동 탐색 120초(승인 대기 제외, 거절로 새 루프가 시작되면 다시 셈), 같은 도구 같은 인자 3회 | `test_stop_conditions_follow_limits`, `test_loop_limit_stops_after_rejection` |
| Context | `agent/app/harness/context.py` | 입력 6000 토큰 예산, 우선순위 낮은 덩어리부터 축약, 이전 루프는 거절 사유만 남겨 요약 | `test_low_priority_sections_are_trimmed_first`, `test_old_loops_are_summarized` |
| Reflection(자체 검토) | `agent/app/graph/nodes.self_review`, `prompts/self_review.md` | 승인 요청 전 승인자 입장 채점(근거, 거절 보완, 최적화, 설명, 위험 각 20점, 합계는 코드 계산). 80점 미만이면 설명 보완, 다른 조합, 근거 추가 중 하나로 다시 구성하고 점수가 정체되면 방법을 바꿈. 5회가 되면 최고점 회차 안으로 승인 요청 | `test_review_below_threshold...`, `test_review_stops_after_five_rounds...`, `test_review_switches_method...` |
| State/Memory | LangGraph PostgresSaver, PostgresStore | thread_id = event-이벤트ID, 승인 대기 후 같은 thread로 재개, 거절 이력 장기 메모리 | `test_first_loop_stops_at_approval...`, `test_rejection_becomes_constraint...` |
| Guardrails | `agent/app/harness/guardrails.py`, `nodes.validation_gate`, `nodes.constraints_for_issues` | 변경 도구는 interrupt 뒤 승인 플래그가 있어야 실행, 개인정보 마스킹, 도구 결과는 데이터 태그로 격리, 근거 없는 PASS는 WARN으로 강등, 거절 시 고르지 않은 요소를 건드리는 모델 제약은 버림 | `test_destructive_tool_needs_approval_flag`, `test_pass_without_evidence...`, `test_constraints_outside_chosen_issues_are_dropped` |
| Recovery | `agent/app/harness/recovery.py`, `worker.py` | 429, 503은 백오프로 2회 재시도 후 대체 모델(gpt-4.1-mini), 작업 실패는 큐 재시도 3회 후 DLQ와 FAILED | `test_retry_twice_then_fallback`, `test_all_models_failing...` |
| Observability | `agent/app/harness/observability.py` | LangSmith trace(trace_id, task_id, 프롬프트 버전), 진행 이벤트, 노드와 도구 지연, Token, 비용, 재시도와 대체 모델 건수 | 평가 결과표 |

멈춤 조건(탈출 조건)은 `LOOP_LIMIT`, `TOOL_LIMIT`, `TIME_LIMIT`, `NO_FEASIBLE_PLAN`입니다. 1/2/3안이 바닥나면 한 번은 4안 장소를 구성해 다시 평가하고, 4안까지 막히거나 한도에 걸리면 지금까지의 최선안과 위반 사유, 추천 장소를 사람에게 넘깁니다.
