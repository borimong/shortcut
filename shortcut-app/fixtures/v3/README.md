# V3 실제 데이터 연결: 오후 블록 어댑터

이 설정은 공개 V3 데이터(극한업무)를 실제 DB 시드와 RAG 코퍼스로 사용한다. 기존 앱과 평가 코드를 유지하면서 실행할 수 있는 **오후 블록의 부분 평가**다. V3 전체 35개 계획 사례의 통과를 의미하지 않는다.

## 연결된 데이터

- 촬영일 2026-10-23 고정. 배우 5명, 장소 8곳, 장비 13개, 씬 24개를 원본에서 변환한다.
- AM: S001~S008 / 09~11시 / LOC-EXT 고정. PM: S009~S024 / 13~17시 / LOC-INT가 기본.
- PM 대안 장소는 LOC-STUDIO(앱 ID 4), LOC-HUB(앱 ID 6). 원래 장소 LOC-INT는 ID 2.
- 원본 ID ↔ 앱 숫자 ID는 `mapping.json`, 원본 공개 자료는 `agent_inputs/`에 있다.
- RAG 37문서와 어댑터 적용 규칙 1문서를 색인한다. `index_in_rag=false`인 견적·대본과 평가자 정답은 색인하지 않는다.
- 배우 계약 ID는 소문자로 변환한다. 드론은 추가하지 않는다. 기본 장비는 1,4,7,10,12, 대체 카메라는 2다.
- 앱 1/2/3안은 **오후 전용 조합**이다. 원본 V3 전일 PLAN-1/2/3 및 채점 정답과 같지 않다.

## 실행

Docker Desktop을 실행하고 `shortcut-app/.env`에 기존 실행용 설정을 준비한다. 프로젝트 폴더 `shortcut-app`에서:

```sh
bash scripts/v3.sh up
```

화면 http://localhost:18888 / API http://localhost:18880. 기존 로그인 계정과 비밀번호 `shortcut1234`를 사용한다. 별도 Compose 프로젝트 `shortcut-v3` 및 DB 볼륨을 사용하므로 기존 앱 데이터와 섞이지 않는다. RabbitMQ 관리 포트도 15673으로 분리한다. `down`은 볼륨을 지우지 않는다.

RAG 색인이 끝난 뒤 같은 폴더에서 `.env`의 INTERNAL_TOKEN 값을 환경에 설정하고 실행한다. 평가 전용 Python 환경은 `evals/.venv`에 준비했다. 다른 PC에서는 `python3 -m venv evals/.venv`와 `evals/.venv/bin/python -m pip install -r evals/requirements.txt`로 준비한다.

```sh
evals/.venv/bin/python -m evals.run_v3 --label v3 --only v3_main_replan
evals/.venv/bin/python -m evals.run_v3 --label v3_all
```

결과는 `outputs/eval_v3*.json`, `.md`. 자동 평가는 각 시나리오 전에 reset 및 실제 DB 조건 주입을 수행한다. Agent 장기 기억은 원래 평가 코드대로 초기화하지 않는다. 반복 평가 시 이전 실행 기억이 영향을 줄 수 있다.

## 화면에서 직접 시연

내부 토큰을 사용해 아래 두 API를 순서대로 호출한 뒤 화면에서 사건을 접수한다. 이름만 적고 DB를 그대로 두면 조건이 바뀌지 않는다.

```sh
curl -X POST http://localhost:18880/internal/test/reset -H "X-Internal-Token: $INTERNAL_TOKEN"
curl -X POST http://localhost:18880/internal/test/v3/case -H "X-Internal-Token: $INTERNAL_TOKEN" -H 'Content-Type: application/json' -d '{"name":"noise"}'
```

`noise`: 원래 실내 장소 오후 사용 불가. `camera_failure`: 카메라 A 고장. `no_interiors`: 세 실내 장소 전부 오후 사용 불가. `rain_after_exteriors`: 오후 강수확률 80%. `baseline`: 원복. 준비 API는 V3 프로필에서만 열리며 기존 내부 토큰 인증을 사용한다.

## 평가 해석의 경계

전일 6묶음 재정렬, 날짜 이월, 분장석/배우별 콜타임, 정교한 이동 행렬, 취소·협의·이동 비용, 프로젝트/회차 누적 예산, 주간 이력, 원본 승인 정책 전체, 안전 중지/재개는 이번 연결에서 구현하지 않았다. 배우 주간 사용시간 0은 앱 투영용 값이며 원본 사실이 아니다. 비용은 앱의 장소+장비 부분 견적이므로 V3 정답의 전일 총 추가비용과 비교하면 안 된다. 예약·배포도 기존 앱의 목업 동작이다.

원본 전체 사례는 `agent_inputs/cases/demo_cases.json`에 보존한다. 현재 실행 가능한 조정 시나리오는 `../../evals/V3_SCENARIOS.md`를 본다. `build_fixture.py`는 공개 스냅샷에서 SQL·ID 매핑·37개 원본 RAG 문서를 재생성한다.

## 공유된 실행 결과

[2026-10-21 실제 평가 결과](../../docs/evaluation/v3-2026-10-21/SUMMARY.md): Agent 6/9, DB·백엔드 11/11. 실패 3건을 포함한 결과이며 전체 V3 평가가 아니다. 평가 당시 버전과 최신 main 통합 여부는 해당 보고서의 재현 정보를 참고한다.
