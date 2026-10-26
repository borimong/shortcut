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
| ops-mcp | FastMCP 4.1 (`mcp/ops-mcp`) | 확정 뒤 실행팀 도구 18개(장소 예약, 장비 렌탈, 촬영 허가, 차량, 연락, 장부). 시연용 가상 업체로 backend `/internal/**` 호출 | 내부 |
| postgres | PostgreSQL 16 + pgvector | 업무 데이터(app), 임베딩(rag), checkpointer와 장기 메모리(agent) | 내부 |
| rabbitmq | RabbitMQ 3.13 | `agent.tasks`, `jobs.callsheet` 큐와 retry, DLQ | 관리 화면만 로컬 |

MCP 서버 코드는 `mcp/` 폴더에 있습니다. business-mcp와 rag-mcp는 D 담당 안윤태 작성(설명은 `mcp/README.md`), ops-mcp는 Phase 2에 추가했습니다.

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
   docker compose logs -f rag-indexer   # 규정 문서 12건 색인 확인 후 종료
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

날씨 예보: 장소 위경도로 Open-Meteo 시간별 강수량(키 없음)을 1시간마다 받아 씁니다. API가 실패하면 마지막으로 받은 예보를 쓰고, 촬영판과 콜시트 날씨 칸에 예보 출처와 갱신 시각이 보입니다. 변경 입력으로 넣은 강수량은 어느 예보보다 우선합니다. 시연 날 비가 오지 않으면 관리자 화면 운영 설정에서 "시연용 고정 예보"(1회차 한강 공원 13시부터 시간당 8mm)로 바꾸거나, 변경 입력에서 강수량을 넣어 우천 시나리오를 돌립니다. 인터넷이 없으면 `.env`에서 `WEATHER_FETCH_ENABLED=false`로 끄고 고정 예보로 바꿉니다.

## 테스트와 평가

```bash
# 단위 테스트 (네트워크, DB 없이)
cd agent && python -m pytest -q
cd mcp/business-mcp && python -m pytest -q   # MCP 서버 코드는 mcp/ 폴더에 있다 (설명은 mcp/README.md)
cd mcp/rag-mcp && python -m pytest -q
cd mcp/ops-mcp && python -m pytest -q
cd backend && mvn -q test

# 실제 서비스로 평가 시나리오 7개 실행 (compose 실행 중, .env의 INTERNAL_TOKEN과 같은 값을 넘긴다)
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
| Agent Loop | `agent/app/config.py`, `graph/builder.py` | 루프 5회, 도구 호출 120회(실측 첫 루프 41회, 거절 뒤 루프마다 근거 재수집 20회 이상, 4안 구성과 자체 검토의 후보 교체 검증 포함), 자체 검토 80점 통과와 최대 5회, 루프마다 자동 탐색 120초(승인 대기 제외, 거절로 새 루프가 시작되면 다시 셈), 같은 도구 같은 인자 3회 | `test_stop_conditions_follow_limits`, `test_loop_limit_stops_after_rejection` |
| Context | `agent/app/harness/context.py` | 입력 6000 토큰 예산, 우선순위 낮은 덩어리부터 축약, 이전 루프는 거절 사유만 남겨 요약 | `test_low_priority_sections_are_trimmed_first`, `test_old_loops_are_summarized` |
| Reflection(자체 검토) | `agent/app/graph/nodes.self_review`, `prompts/self_review.md` | 승인 요청 전 승인자 입장 채점(근거, 거절 보완, 최적화, 설명, 위험 각 20점, 합계는 코드 계산). 80점 미만이면 설명 보완, 다른 조합, 근거 추가 중 하나로 다시 구성하고 점수가 정체되면 방법을 바꿈. 5회가 되면 최고점 회차 안으로 승인 요청 | `test_review_below_threshold...`, `test_review_stops_after_five_rounds...`, `test_review_switches_method...` |
| State/Memory | LangGraph PostgresSaver, PostgresStore | thread_id = event-이벤트ID, 승인 대기 후 같은 thread로 재개, 거절 이력 장기 메모리 | `test_first_loop_stops_at_approval...`, `test_rejection_becomes_constraint...` |
| Guardrails | `agent/app/harness/guardrails.py`, `nodes.validation_gate`, `nodes.constraints_for_issues` | 변경 도구는 interrupt 뒤 승인 플래그가 있어야 실행, 개인정보 마스킹, 도구 결과는 데이터 태그로 격리, 근거 없는 PASS는 WARN으로 강등, 거절 시 고르지 않은 요소를 건드리는 모델 제약은 버림 | `test_destructive_tool_needs_approval_flag`, `test_pass_without_evidence...`, `test_constraints_outside_chosen_issues_are_dropped` |
| Recovery | `agent/app/harness/recovery.py`, `worker.py` | 429, 503은 백오프로 2회 재시도 후 대체 모델(gpt-4.1-mini), 작업 실패는 큐 재시도 3회 후 DLQ와 FAILED | `test_retry_twice_then_fallback`, `test_all_models_failing...` |
| Observability | `agent/app/harness/observability.py` | LangSmith trace(trace_id, task_id, 프롬프트 버전), 진행 이벤트, 노드와 도구 지연, Token, 비용, 재시도와 대체 모델 건수 | 평가 결과표 |

멈춤 조건(탈출 조건)은 `LOOP_LIMIT`, `TOOL_LIMIT`, `TIME_LIMIT`, `NO_FEASIBLE_PLAN`입니다. 1/2/3안이 바닥나면 한 번은 4안 장소를 구성해 다시 평가하고, 4안까지 막히거나 한도에 걸리면 지금까지의 최선안과 위반 사유, 추천 장소를 사람에게 넘깁니다.

## Phase 2 변경 (phase1-end 이후)

Phase 1(AI Agent Capstone) 제출 시점은 `phase1-end` 태그(ddf32a7)입니다. 이후 병합된 변경은 다음과 같습니다.

| PR | 내용 | 작성 |
|---|---|---|
| #3 | 백엔드 리팩토링(역할과 상태 상수 정리), 승인 흐름 테스트 | 최준형 |
| #4 | 대본 씬 촬영 장소, 지워진 콜시트 배포 건너뜀, 배우 여럿 일정의 조정 시간 | 신지호 |
| #5 | 근거 인용 범위(적용 장소, 문서 종류) 검사, 자체 검토를 코드 계산과 인용 확인 질문으로 교체, 평가 3종 | 김현수 |
| #6 | 재난 문자 0건 조회 결과를 근거로 인정, 확정 뒤 실행팀(6 Agent, ops-mcp), 생각 기록 수정 요청, 근거 루프 개선 | 김현수 |
| #7 | 장부 번호 목록, 재확인 후보, 생각 기록 누락 수정 | 김현수 |
| #8 | 대본과 배우 날짜별 일정 교차검증, 블록 안 씬 순서 바꾸기, 재계획 중단과 되돌리기, 실시간 날씨 예보, 스키마 정리 | 신지호 |

## 평가 결과 (Phase 1 대 Phase 2)

같은 평가셋을 Phase 1 코드(개선 전)와 현재 main(개선 후)으로 쟀습니다. 결과 파일은 [`evals/results/`](evals/results/)에 있습니다.

| No. | 평가셋 | 규모 | 지표 | Phase 1 (개선 전) | Phase 2 main (개선 후) | 비고 |
|---|---|---|---|---|---|---|
| 1 | 근거 인용 평가 | 시나리오 150, 범주 판정 1,050 | 틀린 근거로 통과한 범주 | 130건 (12.4%) | 3건 (0.3%) | Phase 1 코드 대 main |
| 2 | 근거 인용 평가 | 같은 150개 | 7범주 모두 정답인 시나리오 | 30/150 | 125/150 |  |
| 3 | 자체 검토 채점 (본 세트) | 결함 주입 274건 x 3회 | 균형 정확도 | 0.709 | 0.986 | 결함 안 탈락 0.525 → 0.972 |
| 4 | 자체 검토 채점 (별도 세트) | 결과를 보기 전 만든 215건 | 균형 정확도 | 0.589 | 0.923 | 별도 세트를 보기 전 마지막 측정 |
| 5 | 통합 시나리오 | Phase 1 공통 5개 | 기대 결과 일치 | 5/5 (확정까지) | 5/5 (실행까지) | Phase 2는 확정 뒤 실행까지 판정 |
| 6 | 통합 시나리오 비용 | 공통 5개 평균 | 토큰, 응답 시간 | 34,813토큰, 33.0초 | 159,707토큰, 141.6초 | 실행팀 6 Agent 포함 |
| 7 | 단위와 통합 테스트 | agent, MCP, backend | 통과한 테스트 수 | 116개 | 274개 | 모두 통과 |

- 통합 시나리오 7개(Phase 1 공통 5개에 실행 단계 충돌, 씬 순서 조정 추가)는 현재 main에서 7/7입니다(2026-10-26, 1회 측정).

| 평가 | 실행 명령 (shortcut-app 폴더) | 결과 파일 (`evals/results/`) |
|---|---|---|
| 근거 인용 | `python -m evals.constraint_citation --corpus full --label <이름>` | `phase1_constraint_citation.md`, `phase2_constraint_citation.md` |
| 자체 검토 채점 | `python -m evals.review_judge --label <이름>` | `phase1_review_judge*.md`, `phase2_review_judge*.md` |
| 통합 시나리오 | `INTERNAL_TOKEN=... python -m evals.run_eval --label <이름>` | `phase1_eval.md`, `phase2_eval.md` |
| 검색 품질(참고, 개선 전 측정만) | rag-mcp 이미지 안에서 `python -m evals.rag_retrieval --label baseline` (파일 머리말 참고) | `phase1_rag_retrieval.md` |

- 자체 검토 별도 세트(4행)는 결과를 보기 전에 독립 수치로 남긴 2026-10-23 코드 측정값입니다. 본 세트(3행)는 현재 main으로 다시 쟀고, PR #8에서 하드 제약에 대본(SCRIPT) 범주가 들어와 케이스 체크리스트에 대본 근거 1건을 더했습니다.
- 근거 인용 평가의 개선 후 값은 운영 코퍼스를 Phase 1과 같은 8문서로 고정하고 쟀습니다. main에 새로 들어온 문서 4개(배우 D, E 계약서, 합정 허가서, 대본)는 정답 라벨이 없어 넣으면 평가셋이 달라지기 때문입니다.
- 통합 시나리오는 그날 실제 날씨와 상관없이 같은 조건이 되도록 시드 고정 예보로 돕니다(`run_eval.py`의 `EVAL_SETTINGS`). 화면 시연도 비가 오지 않으면 같은 고정 예보를 씁니다.
- 평가 시나리오, 정답 라벨, 확장 코퍼스는 합성 자료라 현업 검수 전 참고치입니다.

## 데이터 출처

| 자료 | 위치 | 출처와 성격 |
|---|---|---|
| 배우 출연 계약서 5종 | `mcp/rag-mcp/corpus/contract-actor-*.md` | 시연용으로 팀이 만든 가상 계약서 |
| 근로기준법 근로시간 조항 요약 | `mcp/rag-mcp/corpus/law-labor-standards.md` | 공개 법령(근로기준법) 요약, 법률 자문 아님 |
| 촬영 허가 조건(한강공원, 합정 루프탑), 드론 비행 금지 안내, 재난과 기상 촬영 중지 기준, 제작비 승인 규정 | `mcp/rag-mcp/corpus/` | 시연용으로 팀이 만든 샘플 문서 |
| 드라마 대본 「봄, 봄」 | `mcp/rag-mcp/corpus/script-ep07-v1.md` | 김유정 원작(1935, 저작권 보호기간 만료)의 줄거리만 빌려 새로 쓴 각색 |
| 날씨 예보 | backend `WeatherForecastService` | Open-Meteo 시간별 예보 API(키 없음, CC BY 4.0) |
| 장소, 장비, 배우, 스태프, 예약 시드 | `backend/src/main/resources/data.sql` | 가상 데이터. 업체 이름은 시연용 표기 |
| 평가 시나리오, 정답 라벨, 확장 코퍼스 54문서 | `evals/` | 평가용 합성 자료 |

실존 인물의 개인정보는 없습니다. 계약서와 시드의 인물은 모두 가상입니다.

## 보안

- 비밀값(OpenAI, LangSmith 키, `JWT_SECRET`, `INTERNAL_TOKEN`)은 `.env`에만 두고 저장소에는 `.env.example`만 올립니다. `.env`는 `.gitignore`로 막습니다.
- 화면과 업무 API는 JWT로 인증하고 역할별로 승인 권한을 나눕니다. MCP 서버가 부르는 `/internal/**`은 `INTERNAL_TOKEN`이 있어야 합니다.
- Agent는 노드별 허용 도구만 부를 수 있고, 예약과 확정 같은 변경 도구는 승인 플래그가 있어야 실행됩니다. 도구 결과의 개인정보는 마스킹합니다(Harness 명세의 Guardrails).

## 역할과 기여

| 이름 | 역할 | phase1-end 이후 병합된 PR |
|---|---|---|
| 김현수 | R2 AI Engineer (흐름), 발표 | #5, #6, #7 |
| 임지현 | R1 PM, AI Engineer | - |
| 신지호 | R5 Frontend, AI Engineer | #4, #8 |
| 정원규 | R6 QA, Eval | - (#2 열림) |
| 안윤태 | R4 Backend, Tool | - (Phase 1 MCP 서버 #1) |
| 최준형 | R4 Backend, Tool | #3 |
