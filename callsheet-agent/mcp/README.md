# mcp/ — D 담당: business-mcp, rag-mcp (계약 rc2)

아키텍처 v2(Notion ShortCut)를 교안 기준 **MCP 서버 2개**로 구현한 코드다. 검증·점수 계산은 **Spring Boot**(C)가 하고,
MCP는 호출만 한다. B·C·E가 완성되기 전에도 개발·테스트할 수 있도록 **mock-backend**를 함께 둔다.

```
mcp/
├─ business-mcp/      도구 15개 → backend /internal/**
│                     온톨로지 3 · 계획안 5 · 변경 3 · 외부 서비스 4 (v2의 ontology-mcp, external-mcp를 합침)
├─ rag-mcp/           도구 3개(search_regulation, search_contract_clause, get_source) + Resource doc://{docId}/{section}, doc://index
├─ mock-backend/      Spring Boot /internal/** 흉내 (Starlette)
│   └─ mock_backend/engine.py   제약·점수 엔진 참조 구현 = C가 Java로 옮길 정답지 (contracts/ENGINE.md)
├─ scripts/smoke_http.py        세 서버를 띄운 뒤 v2 시나리오를 HTTP로 한 바퀴 점검
├─ docker-compose.dev.yml       D 개발용 compose (mock-backend 포함)
└─ requirements-dev.txt
data/docs/            가상 문서 10개: 근로기준법 요약, 계약 운영 가이드, 한강 촬영 허가, 파주 촬영 제한 구역, 출연 계약서 6개(A04는 v2·v3)
```

## 1. 빠르게 시작하기

```bash
cd mcp
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

(cd business-mcp && pytest -q)     # 11개
(cd rag-mcp && pytest -q)          # 7개
```

```bash
# 터미널 1: mock backend
cd mcp/mock-backend && uvicorn mock_backend.app:app --port 8080
# 터미널 2: business-mcp  → http://localhost:9101/mcp
cd mcp/business-mcp && BACKEND_URL=http://localhost:8080 python -m business_mcp.server
# 터미널 3: rag-mcp       → http://localhost:9102/mcp  (첫 실행 때 ./index에 색인)
cd mcp/rag-mcp && RAG_DOCS_DIR=../../data/docs python -m rag_mcp.server
# 터미널 4: v2 시나리오 점검
cd mcp && python scripts/smoke_http.py
```

`smoke_http.py`가 보여주는 흐름 (Agent가 할 순서와 같다):
1. 13시 이후 한강 우천 → `find_impacted_entities` → 영향 블록 B2, 배우 A01·A04, A04 현재 계약서 v3
2. `search_regulation`(촬영 허가 3.1), `search_contract_clause`(contract-A04-v3 5.4)
3. `evaluate_plans` → 27개 중 5개 가능, 최적안 **장소 2안 + 장비 1안 + 시간대 2안**
4. `validate_plan` → `save_plan` → 변경안 v8, 필수 승인자 9명
5. 동시녹음팀장 거절 → `EXCLUDE_LOCATION` 제약 → 최적안 **장소 3안 + 장비 3안 + 시간대 1안** → v9
6. 승인 전 `commit_plan` → `APPROVAL_REQUIRED`로 막힘
7. 전원 승인 → `commit_plan` → 확정 v9, 콜시트 배포 작업 → `link_entity`

docker로 한 번에: `docker compose -f mcp/docker-compose.dev.yml up --build`

## 2. 환경 변수

| 변수 | 기본값 | 쓰는 곳 |
| --- | --- | --- |
| `BACKEND_URL` | `http://backend:8080` | business-mcp |
| `INTERNAL_TOKEN` | `dev-internal-token` | business-mcp, mock-backend |
| `HOST`, `PORT` | `0.0.0.0`, 9101 / 9102 | 두 MCP 서버 |
| `RAG_DOCS_DIR`, `RAG_INDEX_DIR` | `../../data/docs`, `./index` | rag-mcp, 색인기 |
| `EMBEDDING_PROVIDER` | `hash` | `hash`(개발용) 또는 `openai` |
| `EMBEDDING_MODEL`, `OPENAI_API_KEY` | `text-embedding-3-small`, 없음 | openai일 때 |

색인과 검색은 같은 Embedding 모델이어야 한다. 모델 이름·차원은 `index/meta.json`에 남고, 다르면 서버가 `IndexMismatchError`로 멈춘다.

## 3. 다른 역할과 맞물리는 지점

### E(Agent)
- business-mcp 도구는 모두 `ctx` = `{id, role, projectId, taskId}`를 받는다. 모델이 채우면 안 되므로 스키마에서 빼고 호출할 때 넣는다.

```python
def hide_ctx(input_schema: dict) -> dict:
    s = dict(input_schema)
    s["properties"] = {k: v for k, v in s.get("properties", {}).items() if k != "ctx"}
    s["required"] = [r for r in s.get("required", []) if r != "ctx"]
    return s

async def call_business(client, name, args, state):
    return await client.call_tool(name, {**args, "ctx": {**state["user"], "taskId": state["task_id"]}})
```

- 오류 태그로 처리를 나눈다: `[RETRYABLE]` 재시도, `[APPROVAL_REQUIRED]` 승인 대기로, `[STALE_PLAN]` evaluate_plans부터 다시,
  `[HARD_VIOLATION]` 다른 조합 선택, `[SUPERSEDED]`(rag) 현재 계약서 docId로 다시 검색.
- 거절 사유는 `ExtraConstraint`로 바꿔 `evaluate_plans(extra_constraints=...)`에 넣는다. 예시: `contracts/examples/extra-constraint.json`
- 감독 지시는 `weights`로 바꿔 넣는다. 예산 한도(HARD)는 가중치와 상관없이 유지된다.
- 한 루프에 `evaluate_plans` 1회로 27개 조합을 평가하므로 도구 호출 한도 20회 안에 루프 3회가 들어간다.

### B·C(backend, 제약·점수 엔진)
- 경로, 헤더, 응답, 오류 형식은 `contracts/openapi-internal.yaml`. mock-backend가 그대로 구현돼 있다.
- 엔진 규칙은 `contracts/ENGINE.md`, 참조 구현은 `mock_backend/engine.py`. 8장 기대값으로 Java 구현을 확인한다.
- 실제 backend가 뜨면: `python contracts/tools/check_contracts.py --backend http://localhost:8080`

### A(화면)
- 근거 패널: 위반·검색 결과의 `docId`+`section` → `/api/docs/{docId}/sections/{section}` (backend → agent → rag-mcp Resource)
- 승인 현황 보드·변경안 상세·알림 데이터 형식: `contracts/schemas/api.schema.json`, 예시 `approval-board.json`, `notification-list.json`

## 4. 남은 일 (D)

- [ ] 실제 backend로 전환: `BACKEND_URL` 변경 후 `pytest`, `smoke_http.py`, `check_contracts.py --mcp` 재실행
- [ ] pgvector 저장소 구현 (`rag_mcp/store.py`에 같은 메서드로 추가), compose의 postgres 이미지를 `pgvector/pgvector:pg16`으로 (B와)
- [ ] C의 실제 문서로 재색인, `EMBEDDING_PROVIDER=openai`
- [ ] docstring 튜닝: E와 함께 모델이 도구를 잘못 고른 trace를 보고 고친다
- [ ] 도구 이름·인자를 바꾸면 `mcp-tools.json`을 다시 뽑고 `gen_examples.py`, `check_contracts.py` 실행
