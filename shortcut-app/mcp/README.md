# mcp/ — D 담당: business-mcp, rag-mcp

shortcut-app 전체 스택에 붙는 MCP 서버 2개(교안 기준)다. 이 폴더는 `shortcut-app/mcp/`이고, `shortcut-app/docker-compose.yml`이 빌드한다.

```
Agent(shortcut-app/agent) ──Streamable HTTP──▶ business-mcp :9101/mcp ──X-Internal-Token──▶ backend /internal/**
                          └─Streamable HTTP──▶ rag-mcp      :9102/mcp ──▶ Postgres(pgvector) rag 스키마
```

| 서버 | 도구 | Resource |
| --- | --- | --- |
| business-mcp | 조회 10: get_entity_context, find_impacted_entities, get_plan_set, get_availability, get_weather, get_disaster_alerts, search_locations, evaluate_plans, validate_plan, get_proposal · 쓰기 3: link_entity, register_alternative_locations, submit_proposal · 되돌릴 수 없음 1: commit_plan | 없음 |
| rag-mcp | 조회 2: search_regulation, search_contract_clause · 쓰기 1: index_document · 삭제 1: delete_document | `rag://documents/{doc_id}` 원문, `rag://index/info` 색인 목록·임베딩 모델 |

검증·점수 계산은 Spring Boot 엔진(`backend/.../engine`)이 한다. MCP 서버는 규칙을 갖지 않고 호출만 한다.

## 1. 맞춘 것 (연결 조건)

| 항목 | 기준 파일 | 이 폴더 |
| --- | --- | --- |
| 도구 이름·인자 | `agent/app/graph/*.py`, `agent/app/harness/guardrails.py` (`business_`/`rag_` 접두어 + 이름) | `business_mcp/server.py`, `rag_mcp/server.py` |
| 경로·본문 | `backend/.../web/internal/*Controller.java` | `business_mcp/server.py` |
| 인증 | `InternalTokenFilter` (`X-Internal-Token`, `X-Acting-User`) | `business_mcp/backend.py` (Agent가 MCP 요청에 실은 `X-Acting-User`를 그대로 넘김) |
| 오류 형식 | `agent/app/harness/tools.py`의 정규식 `[CODE] 메시지 (retryable=true\|false)` | `business_mcp/errors.py`: backend 오류 code별로 "다음에 할 일"을 붙인다 |
| 근거 원문 | Agent가 `rag://documents/{doc_id}` 원문에 chunk 원문이 그대로 있는지 확인 | `rag_mcp/chunking.py` (chunk = 원문의 부분 문자열) |
| 환경 변수 | compose | `BACKEND_INTERNAL_URL`, `INTERNAL_TOKEN`, `RAG_DB_DSN`, `OPENAI_API_KEY`, `RAG_MCP_URL` |

## 2. 실행

```bash
# 전체 스택 (shortcut-app 폴더에서, .env 필요)
cd shortcut-app && docker compose up --build
docker compose logs -f rag-indexer        # 코퍼스 8건 색인 후 종료
```

```bash
# 단위 테스트 (네트워크·DB 없이: backend는 httpx.MockTransport, rag는 MemoryStore + HashEmbedder)
pip install -r shortcut-app/mcp/requirements-dev.txt
cd shortcut-app/mcp/business-mcp && python -m pytest -q    # 10개
cd shortcut-app/mcp/rag-mcp && python -m pytest -q         # 10개
```

```bash
# OpenAI 키·Postgres 없이 rag-mcp만 띄워 보기
cd shortcut-app/mcp/rag-mcp
EMBEDDING_PROVIDER=hash RAG_STORE=memory python -m rag_mcp.server
RAG_MCP_URL=http://localhost:9102/mcp python -m rag_mcp.indexer   # 다른 터미널
```

## 3. 환경 변수

| 변수 | 기본값 | 쓰는 곳 |
| --- | --- | --- |
| `BACKEND_INTERNAL_URL` | `http://localhost:8080` (예전 이름 `BACKEND_URL`도 읽음) | business-mcp |
| `INTERNAL_TOKEN` | `local-internal-token` | business-mcp → backend |
| `HOST`, `PORT` | `0.0.0.0`, 9101 / 9102 | 두 서버 |
| `EMBEDDING_PROVIDER` | `openai` | `openai` 또는 `hash`(개발용) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM` | `text-embedding-3-small`, 1536 | openai |
| `RAG_STORE` | `pgvector` | `pgvector` 또는 `memory`(개발용) |
| `RAG_SEARCH_MODE` | `hybrid` | `hybrid`(벡터 + BM25 순위를 RRF로 합침) 또는 `vector`(벡터만, 이전 동작) |
| `RAG_DB_DSN` | `postgresql://shortcut:shortcut@localhost:5432/shortcut` | pgvector |
| `RAG_MCP_URL`, `RAG_CORPUS_DIR` | `http://localhost:9102/mcp`, `rag-mcp/corpus` | indexer |

색인 문서마다 임베딩 모델 이름을 저장한다. 모델이 바뀌면 rag-mcp가 시작할 때 경고하고, indexer가 그 문서들을 다시 색인한다.

## 4. 바뀐 점 (rc2 → shortcut-app 연결판)

- 도구 이름·인자를 shortcut-app Agent에 맞췄다. `ctx` 인자는 없앴다(Agent는 요청자를 MCP 헤더 `X-Acting-User`로 보낸다).
- mock-backend와 `scripts/smoke_http.py`, `docker-compose.dev.yml`은 지웠다. 실제 backend가 생겨 더는 쓰지 않는다(git 기록에 남아 있다).
- rag-mcp: 로컬 파일 색인 → pgvector(rag 스키마), 문서는 backend 시드와 같은 `corpus/` 8건, 도구는 Agent가 쓰는 4개.
- 2026-10-21: 팀원 버전 `shortcut-app/business_mcp`, `shortcut-app/rag_mcp`는 지우고, 이 폴더를 `callsheet-agent/mcp`에서 `shortcut-app/mcp`로 옮겨 MCP 코드를 하나로 합쳤다.
- `callsheet-agent/contracts/`의 rc2 문서는 설계 기록으로만 남긴다.

## 5. 남은 일 (D)

- [ ] 실제 스택에서 `docker compose up` 후 시연 시나리오(우천 → 거절 → 재계획 → 확정) 한 바퀴 확인
- [ ] `evals/run_eval`로 도구 오류 문장(errors.py) 바꾸기 전후 비교
- [ ] docstring 튜닝: LangSmith trace에서 모델이 도구를 잘못 고른 경우를 보고 고친다

## 하이브리드 검색 (Phase 2)

검색 평가(`evals/results/phase1_rag_retrieval.md`)에서 벡터만 쓰면 숫자·법률 용어 질의("야간근로 가산 수당", "22시 이후 촬영 제한")와
구어체 질의에서 1등을 자주 놓쳤다. 그래서 rag-mcp 검색을 하이브리드로 바꿨다(`rag_mcp/hybrid.py`).

1. 도구와 같은 범위(문서 종류, 계약서 한 건)로 벡터 후보를 최대 60개 받는다.
2. 같은 후보를 BM25로 다시 매긴다. 한국어는 어절 안의 글자 두 개씩을 토큰으로 쓴다(형태소 분석기 없음).
3. 두 순위를 RRF(1/(60+순위))로 합쳐 상위 k개를 돌려준다. 결과의 `score`는 예전과 같은 코사인 유사도다.

범위 거르기는 벡터 검색이 먼저 하므로 BM25가 다른 계약서나 범위 밖 문서를 끌어오지 않는다.
`RAG_SEARCH_MODE=vector`로 이전 동작으로 되돌릴 수 있고, 현재 방식은 `rag://index/info`의 `search_mode`에 보인다.

