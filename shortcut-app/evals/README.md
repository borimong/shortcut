> V3 실제 데이터 실행은 [V3_SCENARIOS.md](V3_SCENARIOS.md)와 [연결 안내](../fixtures/v3/README.md)를 참고하세요. 아래 기존 시나리오는 이전 시드 기준입니다.

# 검증 안내서

이 문서를 위에서부터 따라가며 검증한다. **무엇을 확인하는지**는 [SCENARIOS.md](SCENARIOS.md)에 있고, 여기에는 **어떻게 준비하고 어떤 순서로 돌리고 어디에 기록하는지**를 적는다.

| 순서 | 할 일 | 걸리는 시간 | 필요한 것 |
|---|---|---|---|
| 0 | [준비](#0-준비) | 10~20분 (첫 빌드) | Docker, OpenAI 키 |
| 1 | [단위 테스트](#1-단위-테스트) | 수 분 | Python 3.11+, Java 21, Maven |
| 2 | [회귀 시나리오](#2-회귀-시나리오-run_eval) | 시나리오당 1~3분 | 0번 완료 |
| 3 | [대표 시나리오 ① 자동](#3-대표-시나리오--자동) | 5~10분 | 0번 완료 |
| 4 | [대표 시나리오 ⑤ ⑥ 수동](#4-대표-시나리오---수동) | 각 10분 | 0번 완료 |
| 5 | [대표 시나리오 ④ 대안](#5-대표-시나리오--대안-루프-한도) | 5분 | agent 설정 변경 |
| 6 | [기록과 공유](#6-기록과-공유) | | |

②③④는 백엔드 테스트 훅이 생긴 뒤에 돌린다(SCENARIOS.md 7장).

---

## 0. 준비

### 0-1. 환경 변수

`shortcut-app/.env.example`을 `.env`로 복사하고 아래 값을 채운다. **`.env`는 절대 커밋하지 않는다.**

| 변수 | 값 |
|---|---|
| `OPENAI_API_KEY` | 팀에서 받은 키 |
| `JWT_SECRET` | 32자 이상 아무 문자열 |
| `INTERNAL_TOKEN` | 아무 문자열. 아래 내부 API 호출과 `run_eval`에 같은 값을 쓴다 |
| `LANGSMITH_API_KEY` | 있으면 넣는다. 없으면 trace 링크 없이 동작한다 |
| `WORKER_FAIL_FIRST_ATTEMPT` | `true` 그대로 (배포 재시도 확인용) |

### 0-2. 서비스 실행

```bash
cd shortcut-app
docker compose up -d --build
docker compose logs -f rag-indexer      # 규정 문서 8건 색인이 끝나고 컨테이너가 종료될 때까지 본다
docker compose ps                       # rag-indexer 말고 모두 running(healthy)인지 확인
```

| 주소 | 용도 |
|---|---|
| http://localhost:8088 | 화면 |
| http://localhost:18080 | backend API (`run_eval`이 여기로 호출) |
| http://localhost:15672 | RabbitMQ 관리 화면 (계정 `shortcut` / `shortcut`), 큐와 DLQ 확인 |

### 0-3. 계정

비밀번호는 모두 `shortcut1234`이다.

| 계정 | 역할 | 시나리오에서 하는 일 |
|---|---|---|
| `manager` | 제작실장 | 변경 접수, 질문 |
| `director` | 연출감독 | 변경 접수, 모든 변경안 승인·거절 |
| `ad1`, `ad2` | 1·2조감독 | 시간·동선 승인 |
| `sound` | 동시녹음팀장 | 장소 소음 승인·거절 |
| `dop` | 촬영감독 | 장비 승인 |
| `pd` | 제작 PD | 추가 비용 승인·거절 |
| `crew` | 연출부원 | 권한 없음 확인용 |

### 0-4. 자주 쓰는 명령

터미널에서 한 번 설정해 두면 아래 명령을 그대로 쓸 수 있다.

```bash
export SHORTCUT_URL=http://localhost:18080
export INTERNAL_TOKEN=.env에_넣은_값

# 데이터 초기화 (시나리오 시작 전마다)
curl -s -X POST $SHORTCUT_URL/internal/test/reset -H "X-Internal-Token: $INTERNAL_TOKEN"

# 로그인 토큰 받기 (예: manager)
TOKEN=$(curl -s -X POST $SHORTCUT_URL/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"manager","password":"shortcut1234"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")

# 변경 접수
curl -s -X POST $SHORTCUT_URL/api/events -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"shootDayId":1,"type":"RAIN","detail":"13시 이후 한강 강수확률 80%"}'

# 작업 상태
curl -s $SHORTCUT_URL/api/ai/tasks/작업ID -H "Authorization: Bearer $TOKEN"

# 배포 기록과 큐 작업 기록
docker compose exec postgres psql -U shortcut -d shortcut -c "SELECT queue, attempt, status, error, created_at FROM app.job_logs ORDER BY id DESC LIMIT 10;"
docker compose exec postgres psql -U shortcut -d shortcut -c "SELECT callsheet_version_id, channel, status FROM app.distribution_logs ORDER BY id DESC LIMIT 10;"
```

### 0-5. 장기 메모리 초기화

`reset`은 Agent의 거절 기록을 지우지 않는다(SCENARIOS.md 1장 4번). **회귀 시나리오를 before/after로 비교할 때**는 시작 전에 비운다. 대표 ②를 돌릴 때는 비우지 않는다.

```bash
# LangGraph 저장소 테이블. 실행 전 에이전트 담당에게 테이블 이름과 지워도 되는지 확인한다.
docker compose exec postgres psql -U shortcut -d shortcut -c "DELETE FROM agent.store;"
```

---

## 1. 단위 테스트

네트워크와 DB 없이 돌아간다. 하나라도 실패하면 시나리오 전에 해당 역할에 먼저 알린다.

```bash
cd shortcut-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt pytest
pip install -r ../callsheet-agent/mcp/business-mcp/requirements.txt -r ../callsheet-agent/mcp/rag-mcp/requirements.txt

(cd agent && python -m pytest -q)
(cd ../callsheet-agent/mcp/business-mcp && python -m pytest -q)   # compose가 빌드하는 MCP 서버는 이 폴더에 있다
(cd ../callsheet-agent/mcp/rag-mcp && python -m pytest -q)
(cd backend && mvn -q test)
```

`shortcut-app/business_mcp`, `shortcut-app/rag_mcp`는 compose가 쓰지 않는 예전 폴더라 돌리지 않는다.

각 테스트가 무엇을 확인하는지는 SCENARIOS.md 6장에 있다.

---

## 2. 회귀 시나리오 (`run_eval`)

짧은 시나리오 8개를 자동으로 돌린다. 각 시나리오 시작 때 `reset`을 알아서 부른다.

```bash
cd shortcut-app
pip install httpx                       # 1번에서 만든 가상환경이면 이미 있을 수 있다
export INTERNAL_TOKEN=.env에_넣은_값

python -m evals.run_eval --label 날짜_이름 \
  --only rain_approve --only rain_reject_sound --only disaster_alert --only premium_instruction \
  --only fourth_plan_after_rejections --only equipment_reject_director --only cost_reject_producer \
  --only issue_mismatch_sound
```

결과는 `shortcut-app/outputs/eval_<label>.md`(표)와 `.json`(전체 값)에 저장된다.

### 결과 읽기

1. `ok`가 False인 줄을 찾는다.
2. `status`를 본다. `ERROR`면 시나리오 실행 자체가 실패한 것이라 `.json`의 `error`를 본다.
3. `failedChecks`를 본다. 코드의 뜻은 SCENARIOS.md 4장 표에 있다.
4. `traceUrl`(`.json`)로 LangSmith에서 어느 노드에서 무엇을 골랐는지 본다.
5. LLM 결과는 실행마다 다를 수 있다. 실패한 시나리오만 `--only`로 **두 번 더** 돌려 3번 중 몇 번 성공하는지 적는다.

### 변경 전후 비교

프롬프트, 한도, 모델 중 하나를 바꿨을 때만 한다. 0-5대로 메모리를 비운 뒤 같은 시나리오를 돌린다.

```bash
python -m evals.run_eval --label before
# 변경 적용 후
python -m evals.run_eval --label after
python -m evals.run_eval --compare before after   # outputs/eval_compare_before_after.md
```

---

## 3. 대표 시나리오 ① (자동)

```bash
python -m evals.run_eval --label 날짜_main --only main_rain_three_rejections
```

자동으로 확인하는 것: 접수 권한, 중복 접수, 잘못된 승인·거절 4종, 거절 세 번 뒤의 단계별 변화, 4안, 추가 비용 상한, 질의응답 출처, 전화번호 마스킹.

**자동으로 확인하지 않는 것**은 실행 중에 화면을 열어 직접 본다. 시나리오가 끝나기 전에 보려면 `manager`로 로그인해 진행 화면을 띄워 둔다.

- SCENARIOS.md ① 3단계의 탈락 이유 (trace의 `business_evaluate_plans` 결과)
- ① 8단계의 예약 상태 `MANUAL_PENDING`, 배포 재시도 (0-4의 `job_logs`에서 RETRY 다음 성공)
- ① 11단계 변경안 지정 질문 (화면에서 거절된 3차안을 열고 질문)
- ①의 "화면에서 볼 것" 목록

---

## 4. 대표 시나리오 ⑤ ⑥ (수동)

SCENARIOS.md의 표를 한 줄씩 따라간다. 두 시나리오에는 **"확인 필요"** 칸이 있으니, 실제로 나온 결과를 6번 기록표에 그대로 적는다.

- **⑤ 두 변경이 동시에 들어옴**: 브라우저 창 두 개를 띄운다. 하나는 `manager`(작업 A), 다른 하나는 `director`(작업 B)로 로그인한다. B를 먼저 전원 승인해야 하므로, 승인할 역할마다 로그인을 바꾸거나 0-4의 curl로 승인한다.
  ```bash
  curl -s -X POST $SHORTCUT_URL/api/ai/tasks/작업ID/approval -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"proposalId":변경안ID,"decision":"APPROVE"}'
  ```
- **⑥ 도구 서버 장애**: 시작 전 `docker compose stop business-mcp`, 끝나면 반드시 `docker compose start business-mcp`. Agent 작업 DLQ는 RabbitMQ 관리 화면의 Queues에서 확인한다.

---

## 5. 대표 시나리오 ④ 대안 (루프 한도)

agent의 루프 한도를 2로 낮춰야 한다. compose 파일은 고치지 않고 로컬 덮어쓰기 파일을 쓴다. 이 파일은 `.gitignore`에 없어서 `git status`에 보이니, **끝나면 지우고 커밋하지 않는다.**

```bash
cd shortcut-app
cat > docker-compose.override.yml <<'EOF'
services:
  agent:
    environment:
      MAX_LOOPS: "2"
EOF
docker compose up -d agent
python -m evals.run_eval --label 날짜_limit --only main_unsolvable_loop_limit

# 끝나면 원래대로
rm docker-compose.override.yml
docker compose up -d agent
```

`ok`가 False이고 `stopCondition`이 비어 있으면, 한도를 몇 번째 거절에서 넘는지가 예상과 다른 것이다. `proposals`와 `status`를 기록표에 적는다.

---

## 6. 기록과 공유

### 기록표

검증할 때마다 아래 표를 팀 노션(또는 이 폴더의 `outputs/`가 아닌 공유 위치)에 복사해 채운다.

| 시나리오 | 날짜 | 결과 (성공 횟수/시도) | 기대와 다른 점 | `failedChecks` | trace 링크 | 공유한 역할 |
|---|---|---|---|---|---|---|
| 단위 테스트 | | | | | | |
| 회귀 8개 | | | | | | |
| ① | | | | | | |
| ⑤ | | | | | | |
| ⑥ | | | | | | |
| ④ 대안 | | | | | | |

### 실패하면 누구에게

| 실패한 곳 | 공유할 역할 |
|---|---|
| 장소·시간·장비 판정, 승인자 목록, 예산·52시간 위반 | 제약 엔진 |
| 권한, 중복 접수, 알림, 예약 상태, 배포 재시도·DLQ | 백엔드 |
| 노드 흐름, 거절 반영, 4안 키워드, 자체 검토, 마스킹, 질의응답 | 에이전트 |
| 도구 호출 오류, 근거 검색 결과, 원문 Resource | MCP |
| 화면 표시 | 프론트엔드 |

### 문서 고치기

기대와 다른 결과가 **올바른 동작**으로 판단되면(예: 4안이 다른 장소로 나왔지만 규칙상 맞음) SCENARIOS.md의 기대 칸을 고친다. ⑤ 5단계, ⑥의 "확인 필요"는 첫 실행 결과로 채운다.
