# mcp/ — D 담당: business-mcp, rag-mcp

아키텍처 문서 6장(계약 3: `/internal/**`, 사용자 컨텍스트)과 7장(계약 4: MCP 도구, 위반 스키마)을 그대로 구현한 초기 코드다.
B·C·E가 완성되기 전에도 혼자 개발하고 테스트할 수 있도록 **mock-backend**를 함께 둔다.

```
mcp/
├─ business-mcp/      도구 11개 → backend /internal/** 호출 (조회 6, 검증 1, 변경 4)
├─ rag-mcp/           검색 도구 3개 + Resource doc://{docId}/{section}, doc://index
├─ mock-backend/      Spring Boot /internal/**를 흉내 내는 개발용 서버 (Starlette)
├─ scripts/smoke_http.py   세 서버를 띄운 뒤 시연 시나리오 1을 HTTP로 한 바퀴 점검
├─ docker-compose.dev.yml  D 개발용 compose (mock-backend 포함)
└─ requirements-dev.txt
data/docs/            가상 문서 7개 (계약서 3, 허가 규정 2, 제작 지침 1, 대본 1) — C가 실제 문서로 교체
```

## 1. 빠르게 시작하기

```bash
cd mcp
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 테스트 (네트워크·API 키 불필요)
(cd business-mcp && pytest -q)     # 12개
(cd rag-mcp && pytest -q)          # 8개
```

세 서버를 각각 다른 터미널에서 띄운다.

```bash
# 터미널 1: mock backend
cd mcp/mock-backend && uvicorn mock_backend.app:app --port 8080

# 터미널 2: business-mcp  → http://localhost:9101/mcp
cd mcp/business-mcp && BACKEND_URL=http://localhost:8080 python -m business_mcp.server

# 터미널 3: rag-mcp       → http://localhost:9102/mcp  (첫 실행 때 ./index에 색인을 만든다)
cd mcp/rag-mcp && RAG_DOCS_DIR=../../data/docs python -m rag_mcp.server

# 터미널 4: HTTP 점검
cd mcp && python scripts/smoke_http.py
```

docker로 한 번에: `docker compose -f mcp/docker-compose.dev.yml up --build`

## 2. 환경 변수

| 변수 | 기본값 | 쓰는 곳 |
| --- | --- | --- |
| `BACKEND_URL` | `http://backend:8080` | business-mcp |
| `INTERNAL_TOKEN` | `dev-internal-token` | business-mcp, mock-backend (실제 값은 `.env`) |
| `HOST`, `PORT` | `0.0.0.0`, 9101 / 9102 | 두 MCP 서버 |
| `RAG_DOCS_DIR` | `../../data/docs` | rag-mcp, 색인기 |
| `RAG_INDEX_DIR` | `./index` | rag-mcp, 색인기 |
| `EMBEDDING_PROVIDER` | `hash` | `hash`(개발용, 키 불필요) 또는 `openai` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | openai일 때 |
| `OPENAI_API_KEY` | 없음 | openai일 때 |

**색인과 검색은 같은 Embedding 모델이어야 한다.** 모델 이름과 차원은 `index/meta.json`에 기록되고,
서버가 시작할 때 다르면 `IndexMismatchError`로 멈춘다. 모델을 바꿨으면 다시 색인한다.

```bash
cd mcp/rag-mcp
EMBEDDING_PROVIDER=openai OPENAI_API_KEY=sk-... python -m rag_mcp.indexer --docs ../../data/docs --out ./index
```

## 3. 다른 역할과 맞물리는 지점

### E(Agent)에게: `ctx` 주입 (계약 3)

business-mcp 도구는 모두 `ctx` 인자를 받는다. **모델이 채우면 안 되는 값**이므로 Agent가
(1) 모델에게 넘기는 도구 스키마에서 `ctx`를 빼고 (2) 호출할 때 State의 user와 taskId로 넣는다.

```python
def hide_ctx(input_schema: dict) -> dict:
    s = dict(input_schema)
    s["properties"] = {k: v for k, v in s.get("properties", {}).items() if k != "ctx"}
    s["required"] = [r for r in s.get("required", []) if r != "ctx"]
    return s

async def call_business(client, name: str, args: dict, state) -> dict:
    ctx = {**state["user"], "taskId": state["task_id"]}      # {id, role, productionId, taskId}
    return await client.call_tool(name, {**args, "ctx": ctx})
```

rag-mcp 도구에는 `ctx`가 없다.

오류 메시지는 `[CODE]`로 시작한다. `[RETRYABLE]`이 붙은 것만 Harness가 같은 인자로 재시도하고,
나머지는 메시지 내용(비슷한 ID, 가능한 시간대, 힌트)을 보고 모델이 다음 행동을 고른다.
`[APPROVAL_REQUIRED]`는 재시도하지 말고 approval_gate로 가야 한다.

### B(backend)에게: `/internal/**` 응답

mock-backend의 경로, 헤더, 상태 코드, 오류 본문 `{code, message, details}`가 계약과 같다.
실제 backend도 이 형식으로 응답하면 business-mcp는 `BACKEND_URL`만 바꿔서 그대로 동작한다.
`details`에 넣을 값: `SCENE_NOT_FOUND → similar`, `*_NOT_FOUND → available`,
`ACTOR_UNAVAILABLE → available`, `EQUIPMENT_CONFLICT → freeSlots, alternatives`, `HARD_VIOLATION → violations`.

### C(제약 엔진·데이터)에게

- mock의 제약 검증(`mock_backend/app.py`의 `validate_draft`)은 흉내다. 진짜 규칙과 기준값은 C가 정한다.
  mock은 문서 7장에 없는 `SCENE_MISSING`(초안에서 씬이 빠짐)도 내는데, 계약에 넣을지 C와 정한다.
- 문서는 `data/docs/*.md` 형식(맨 위 메타데이터 + `## 5.2 조항 제목`)으로 받는다. 형식은 `rag_mcp/chunker.py` 맨 위 설명 참고.
- 위반 스키마의 `source.docId`, `source.section`은 이 문서의 docId와 조항 번호를 그대로 쓴다.

## 4. 남은 일 (D)

- [ ] 실제 backend로 전환: `BACKEND_URL` 변경 후 `pytest`와 `smoke_http.py` 재실행
- [ ] Vector DB 결정(미결정 2) 후 `rag_mcp/store.py`에 Chroma 또는 pgvector 구현 추가 (메서드 이름 동일하게)
- [ ] C의 실제 문서로 재색인, `EMBEDDING_PROVIDER=openai`로 전환
- [ ] docstring 튜닝: E와 함께 모델이 도구를 잘못 고른 trace를 보고 고친다
- [ ] `/health` 엔드포인트: compose는 지금 포트 연결로 점검한다. FastMCP의 커스텀 라우트로 `/health`를 추가할 수 있다
