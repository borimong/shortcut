# contracts/ — 인터페이스 계약 v1.0.0-rc2 (보관용)

> **현재 기준은 이 폴더가 아니라 shortcut-app 코드다.** 팀 전체 스택(shortcut-app)이 올라오면서 MCP는
> `shortcut-app/backend`의 `/internal/**`와 `shortcut-app/agent`가 부르는 도구 이름에 맞춰 바뀌었다
> (`shortcut-app/mcp/README.md` 참고, MCP 코드는 `shortcut-app/mcp/`로 옮겼다). 아래 rc2 문서와 mcp-tools.json은 설계 기록으로만 남긴다.

서비스와 서비스가 만나는 경계에서 주고받는 **이름, 경로, JSON 형식, 오류 형식**을 미리 정해 둔 약속이다.
각자 자기 모듈 안은 자유롭게 만들되, 경계를 넘는 것은 이 폴더를 따른다.

**rc2 기준**: 아키텍처 v2(Notion ShortCut 최신본) + 팀 결정 2가지
1. MCP 서버는 교안 기준 **2개**(business-mcp, rag-mcp). v2의 ontology·external 도구는 business-mcp에 합쳤다.
2. 검증(HARD 5)·점수(SOFT 6)·요소 재조합·필수 승인자 지정은 **Spring Boot** 제약·점수 엔진(C)이 한다. 명세는 `ENGINE.md`.

## 1. 파일

| 파일 | 계약 | 만드는 쪽 → 쓰는 쪽 |
| --- | --- | --- |
| `openapi-external.yaml` | 외부 API `/api/**`. 202 접수 + 폴링(진행 1~2초, 승인 현황 5초, 알림 30초) | B → A |
| `openapi-internal.yaml` | 내부 API `/internal/**` (온톨로지, 계획안, 변경, 외부 서비스, 이벤트 콜백), agent `/tasks`·`/docs` | B·C → D·E, E → B |
| `ENGINE.md` | 제약·점수 엔진 규칙, 기준값, 기대값 | C → 전원 |
| `mcp-tools.json` | MCP 도구 18개(business 15, rag 3)와 Resource. 코드에서 뽑은 파일 | D → E |
| `schemas/common.schema.json` | 날짜·ID, 역할 16종(3부서), 작업 상태, UserContext, McpCtx, Source, Error | 전원 |
| `schemas/plan.schema.json` | 블록, 1/2/3안, 선택, 추가 제약, 가중치, 점수, 후보, 위반, 검증·평가 결과, 승인자, 변경안, 확정, 예약 | C·B → D·E·A |
| `schemas/domain.schema.json` | 온톨로지, 가용 시간, 날씨·장소·경로·견적, 내부 요청 본문 | B → D |
| `schemas/task.schema.json` | 변경 이벤트, 큐 메시지(START/RESUME), 진행 이벤트 11종 | B ↔ E, B → A |
| `schemas/api.schema.json` | 로그인, 작업, 폴링 응답, 오늘의 촬영판, 변경안 상세, 승인 현황, 알림, 콜시트 | B → A |
| `examples/*.json` | 예시 37개. 대부분 mock-backend의 실제 응답 (`index.json`에 스키마 표시) | 전원 |
| `tools/check_contracts.py` | 계약 점검 도구 | 전원 |
| `tools/gen_examples.py` | 예시를 mock-backend 응답으로 다시 만든다 | D |

## 2. 점검

```bash
pip install -r contracts/tools/requirements.txt
python contracts/tools/check_contracts.py                                   # 계약 파일·예시 (PR마다)
python contracts/tools/check_contracts.py --backend http://localhost:8080   # backend가 계약대로 응답하는지 (B, C)
python contracts/tools/check_contracts.py --mcp http://localhost:9101/mcp --mcp http://localhost:9102/mcp  # 도구 (D)
```

mock-backend와 실제 backend가 둘 다 `--backend`를 통과하면 business-mcp는 `BACKEND_URL`만 바꿔 그대로 붙는다.

## 3. 핵심 흐름 (누가 무엇을 부르나)

1. 화면 → backend: `POST /api/ai/tasks` (ChangeEvent) → 202. backend가 중복 이벤트를 걸러낸다.
2. backend → 큐 `ai.tasks`: `START`. Agent가 Graph 실행.
3. Agent → business-mcp: `find_impacted_entities` → `get_entity_context`(현재 계약서 docId)
4. Agent → rag-mcp: `search_regulation`, `search_contract_clause`(현재 계약서 docId로만)
5. Agent → business-mcp: `evaluate_plans` (backend 엔진이 27개 조합 검증·채점) → `validate_plan` → `save_plan`
6. Agent: interrupt. backend가 승인 현황을 모으고, 전원 승인이면 `RESUME(ALL_APPROVED)`, 1명이라도 거절이면 즉시 `RESUME(REJECTED, rejections)`.
7. 거절이면 Agent가 사유를 `ExtraConstraint`로 바꿔 5로 돌아간다(루프 최대 3회). 승인이면 `request_location_booking`(필요할 때) → `commit_plan`.
8. backend: 확정, Outbox → RabbitMQ Worker가 콜시트 배포·알림. 화면은 폴링으로 본다.

진행 이벤트(`task.schema.json` TaskEvent): `STATUS`, `TOKEN`, `TOOL_START`, `TOOL_END`, `EVALUATION`, `APPROVAL_REQUIRED`, `APPROVAL_UPDATED`(backend 발행), `PLAN_STALE`(backend 발행), `DONE`, `ESCALATED`, `FAILED`.

## 4. 오류 `details` 규칙 (B → D → 모델)

| code | HTTP | details | 모델이 할 일 |
| --- | --- | --- | --- |
| `ENTITY_NOT_FOUND`, `BLOCK_NOT_FOUND`, `PLAN_NOT_FOUND`, `LOCATION_NOT_FOUND`, `PACKAGE_NOT_FOUND` | 404 | `available` (+ `entityTypes`) | 맞는 ID로 재호출 |
| `CANDIDATE_NOT_FOUND` | 404 | `fields` | build_schedule로 다시 만들기 |
| `APPROVAL_REQUIRED` | 409 | `planStatus`, `pendingRoles` | 재호출하지 않고 승인 대기 |
| `STALE_PLAN` | 409 | `currentDataVersion` | evaluate_plans부터 다시 |
| `BOOKING_NOT_NEEDED` | 409 | `locationId` | 예약 없이 commit |
| `HARD_VIOLATION` | 422 | `violations` | 다른 조합 선택 |
| `FORBIDDEN` | 403 | `allowedRoles` | 사용자에게 알림 |
| `VALIDATION_ERROR` | 400 | `fields` | 인자 수정 |
| `INTERNAL` | 5xx | 없음 | 재시도 (Harness) |

## 5. rc1 → rc2에서 바뀐 것

| 영역 | rc1 | rc2 |
| --- | --- | --- |
| 재계획 | LLM 초안 → 검증 → 수정 반복 | 1/2/3안 재평가 + 요소 재조합 (엔진이 27개 전수 평가) |
| 제약 | 위반 유형 9종, `softScore` | HARD 5분류 + 세부 code, SOFT 6개 점수·가중치·총점 |
| 승인 | PD·조감독 1명 | 변경 내용별 필수 승인자(3부서), 거절 사유 → 추가 제약 |
| 역할 | PD, AD, STAFF, MANAGER | 16종 (제작부·연출부·기술부서·출연자·매니저) |
| 헤더 | `X-Production-Id` | `X-Project-Id` (예: drama-ep07) |
| 도구 | business 11, rag 3 | business 15 (온톨로지 3·계획안 5·변경 3·외부 4), rag 3 |
| 화면 실시간 | SSE | 202 + 폴링 (SSE는 선택) |
| 확정 | `confirm` + `send_callsheets` 도구 | `commit_plan` (dataVersion 조건). 콜시트는 backend Outbox → Worker |

## 6. 확정 절차

1. PM(C)이 `contracts/`를 PR로 올리고 아래 표의 확인자를 리뷰어로 지정한다.
2. 각자 자기 칸만 읽는다. 쓰는 쪽은 "필요한 필드가 다 있나", 만드는 쪽은 "실제로 만들 수 있나".
3. 15분 회의에서 7장 결정 사항을 정하고 그 자리에서 고친다.
4. 전원 승인 + `check_contracts.py` 통과 → 병합, 버전 `1.0.0`, 태그 `contracts-v1.0.0`.

| 계약 | 파일 | 만드는 쪽 | 쓰는 쪽 |
| --- | --- | --- | --- |
| 외부 API·폴링 | `openapi-external.yaml`, `api.schema.json` | - [ ] B | - [ ] A |
| 큐·이벤트 콜백 | `task.schema.json`, `openapi-internal.yaml` (`/internal/tasks`, `/tasks`) | - [ ] B | - [ ] E |
| 엔진 규칙·기대값 | `ENGINE.md`, `plan.schema.json` | - [ ] C | - [ ] B  - [ ] E |
| `/internal/**`·오류 details | `openapi-internal.yaml`, `domain.schema.json` | - [ ] B  - [ ] C | - [ ] D |
| MCP 도구 | `mcp-tools.json` | - [ ] D | - [ ] E |
| 승인 현황·변경안 상세 화면 데이터 | `api.schema.json` (`ApprovalBoard`, `PlanDetail`, `NotificationList`) | - [ ] B | - [ ] A |
| 전체 | 위 전부 | - [ ] C (PM) | |

바꾸는 규칙: 추가(선택 필드, 새 code)는 PR + 관련 확인자 1명 + PM. 깨는 변경(이름·타입·필수 변경, 삭제)은 영향받는 확인자 전원. **10/21 오전 이후에는 깨는 변경 금지.**

## 7. 확정 전에 정할 것

| # | 질문 | rc2에 넣은 값 (제안) | 결정 |
| --- | --- | --- | --- |
| 1 | 우천 HARD 기준 강수 확률 | 60% | C |
| 2 | 회차 남은 예산, 장소 적합도·장비 점수 표 | ENGINE.md 3장 값 | C |
| 3 | 필수 승인자 규칙 | Notion 메모(3부서)대로, ENGINE.md 5장 | C, 신지호 님 |
| 4 | 거절 사유 → 추가 제약 4종(EXCLUDE_LOCATION·TIME_WINDOW·PACKAGE, MAX_EXTRA_COST)으로 충분한가 | 4종 | E, C |
| 5 | 진행 상황도 폴링만 쓸지, SSE(`/stream`)도 둘지 | 폴링 필수, SSE 선택 | A, B |
| 6 | 후보(planHash) 보관 기간 | 30분 | B |
| 7 | 재계획 루프·도구 호출·시간 한도 | 3회, 20회, 120초 | E |
