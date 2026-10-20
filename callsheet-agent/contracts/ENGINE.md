# 제약·점수 엔진 명세 (rc2) — Spring Boot 모듈, 담당 C

검증(HARD)·점수(SOFT)·요소 재조합·필수 승인자 지정은 **backend(Spring Boot) 한 곳**에서만 한다.
Agent와 business-mcp는 이 엔진을 호출만 하고 규칙을 다시 구현하지 않는다(교안 금지 사항).

- 참조 구현: `mcp/mock-backend/mock_backend/engine.py` (Python). C는 이것을 Java로 옮긴다.
- 기준 데이터: `mcp/mock-backend/mock_backend/fixtures.py`. C의 시드 데이터로 바꿔도 규칙은 같다.
- 옮긴 뒤 확인: 같은 데이터에서 8장의 기대값이 나와야 하고, `check_contracts.py --backend`가 통과해야 한다.

## 1. 입력과 용어

| 용어 | 뜻 |
| --- | --- |
| 블록 | 같은 장소에서 이어 찍는 씬 묶음. 하루 계획 = 블록 목록 (B1~B4) |
| 1/2/3안 | 블록마다 제작사가 미리 만든 대안 `P1`, `P2`, `P3` |
| 요소 | 장소(`location`), 장비 묶음(`equipment`), 시간대(`time`). 이동 거리는 장소에서 계산 |
| 선택 `choice` | 요소마다 어느 안에서 가져올지. 셋이 다르면 재조합 |
| 후보 | 선택을 적용해 블록 하나를 다시 놓은 하루 계획. `planHash` = sha1(blockId, choice, extraConstraints, dataVersion) 앞 12자리 |
| dataVersion | 원본 데이터(계획, 가용 시간, 예약 등)가 바뀔 때마다 1 증가. 승인 대기 중 바뀌면 변경안은 STALE |

## 2. HARD 제약 5분류 (하나라도 걸리면 후보 제외)

위반 형식: `{category, code, target, detail, source, hint}` (plan.schema.json `Violation`). `source`는 RAG 문서 docId·section.

| 분류 | code | 조건 | source |
| --- | --- | --- | --- |
| SCHEDULE | `SCHEDULE.ACTOR_AVAILABILITY` | 블록 출연 배우의 가능 시간 밖 | 배우 현재 계약서 4.1 |
| SCHEDULE | `SCHEDULE.LOCATION_HOURS` | 장소 이용 가능 시간 밖 | 없음 |
| SCHEDULE | `SCHEDULE.EQUIPMENT_AVAILABILITY` | 장비 묶음 중 하나라도 대여 가능 시간 밖 | 없음 |
| SCHEDULE | `SCHEDULE.OVERLAP` | 다른 블록과 같은 장소 또는 같은 배우로 시간이 겹침 | 없음 |
| SCHEDULE | `SCHEDULE.TRAVEL` | 바뀐 블록과 앞뒤 블록 사이 간격 < 이동 시간 | 없음 |
| SCHEDULE | `SCHEDULE.OUTDOOR_RAIN` | 야외 장소이고 블록 시간대의 최대 강수 확률 ≥ **60%** | permit-hangang 3.1 |
| SCHEDULE | `SCHEDULE.APPROVER_CONDITION` | 거절 사유 추가 제약(EXCLUDE_LOCATION·TIME_WINDOW·PACKAGE)에 걸림 | 없음 |
| CONTRACT | `CONTRACT.NIGHT_BAN` | 출연 계약의 야간 금지 시각 이후 종료 | 계약서 5.4 |
| CONTRACT | `CONTRACT.DAILY_MAX` | 배우 오늘 근무 > 계약 1일 최대 시간 | 계약서 5.2 |
| LAW | `LAW.WEEKLY_52H` | 배우 이번 주 누적 + 오늘 근무 > **52시간** | law-labor 53 |
| LAW | `LAW.BREAK` | 배우 연속 근무 구간 > **4시간** (30분 이상 쉬어야 구간이 끊김) | law-labor 54 |
| LAW | `LAW.PERMIT` | 야외 장소의 촬영 허가가 없거나 허가 시간 밖 | permit-hangang 2.3 |
| BUDGET_LIMIT | `BUDGET_LIMIT.EPISODE` | 추가 비용 > 회차 남은 예산 | 없음 |
| BUDGET_LIMIT | `BUDGET_LIMIT.APPROVER_CONDITION` | 추가 제약 MAX_EXTRA_COST 초과 | 없음 |
| NO_FILMING_ZONE | `NO_FILMING_ZONE.DRONE` | 드론 포함 장비 묶음 + 드론 금지 장소 | 장소의 zone 문서 2.1 |

계산 규칙
- **배우 오늘 근무(분)** = 출연 블록 길이 합 + 출연 블록 사이 이동 시간(장소가 다를 때).
- **연속 근무 구간**: 출연 블록을 시간순으로 보며 `다음 시작 − 이전 끝 − 이동 시간 < 30분`이면 이어진 것으로 본다.
- **우천**: 블록이 걸친 각 정시(13:00~13:59는 13시)의 강수 확률 중 최댓값.
- 배우의 계약 조건은 온톨로지의 **현재 버전(CURRENT)** 계약서만 쓴다. SUPERSEDED 버전은 무시한다.

## 3. SOFT 점수 6개 (0~1, 높을수록 좋음)

| 기준 | 계산 |
| --- | --- |
| location | 장면 의도별 장소 적합도 표 (예: 맑은 날 야외 산책 → 한강 0.95, 성수 0.75, 파주 0.60) |
| equipment | 장비 묶음 × 실내/야외 표 (기존 렌탈 야외 1.0·실내 0.8, 추가 조명 야외 0.8·실내 1.0, 최소 장비 0.6) |
| weather | 야외: 1 − 최대 강수 확률/100, 실내: 1.0 |
| budget | max(0, 1 − 추가 비용 / 회차 남은 예산) |
| time | max(0, 1 − 0.5 × max(0, 하루 길이시간 − 8)/6 − 0.5 × 대기분/240). 대기 = Σ max(0, 블록 간격 − 이동 시간) |
| distance | max(0, 1 − 하루 총 이동 km / 120) |

**총점 = Σ(가중치 × 점수)**. 가중치는 6개 모두 0 이상, 합으로 나눠 정규화한다.
기본 가중치: location 0.25, equipment 0.15, weather 0.15, budget 0.20, time 0.10, distance 0.15.
감독 지시(예: "웃돈을 줘도 좋은 데로")는 Agent가 가중치로 바꿔 넘긴다. **예산 한도(HARD)는 가중치와 상관없이 유지**한다.

## 4. 1/2/3안 재평가와 요소 재조합 (`/internal/plans/evaluate`)

1. 요소 3개 × 안 3개 = **27개 조합**을 모두 후보로 만든다.
2. 각 후보를 HARD로 검사해 위반이 없는 것만 남긴다. 위반 code별 개수는 `infeasibleByCode`.
3. 남은 후보를 **총점 내림차순 → 추가 비용 오름차순 → choice 사전순**으로 정렬해 상위 `top`(기본 5)개를 `ranked`로 돌려준다.
4. `originalPlans`: 원래 1/2/3안(요소가 모두 같은 안) 각각의 가능 여부와 총점.
5. `ranked`가 비면 세 안 모두 불가 → Agent가 사람에게 넘긴다(ESCALATED, 4안 추천은 확장).
6. `ranked` 후보의 planHash는 바로 validate·save에 쓸 수 있도록 보관한다(보관 기간은 B가 정한다. 권장 30분).

## 5. 필수 승인자 지정 (`/internal/plans` 저장 시)

변경 내용(`changes`)에 따라 자동 지정한다 (Notion 메모, 3부서). 부서장 아래 팀원은 승인하지 않고 알림만 받는다.

| 바뀐 것 | 필수 승인자 |
| --- | --- |
| 장소 | 연출감독(DIRECTOR), 촬영감독(DOP), 조명감독(GAFFER), 미술감독(ART_DIRECTOR), 동시녹음팀장(SOUND_LEAD), 제작실장(PRODUCTION_MANAGER: 섭외·예약) |
| 장비 묶음 | 촬영감독(DOP), 그립실장(GRIP_CHIEF) |
| 시간대·콜타임 | 1조감독(AD1), 조명감독(GAFFER), 의상·분장실장(COSTUME_MAKEUP) |
| 동선·이동 거리 | 2조감독(AD2) |
| 추가 비용 > 0 | 제작 PD(PRODUCTION_PD) |
| 항상 | 제작실장(PRODUCTION_MANAGER: 일정 확정) |

중복은 한 번만, `scope`에 이유를 이어 붙인다. 사람에게 넘길 때: 일정·순서 문제는 1조감독, 예산 한도 문제는 책임 프로듀서.

## 6. 변경안 상태와 확정

```
PENDING_APPROVAL ─전원 승인→ APPROVED ─commit→ COMMITTED
       │                       │
       └─1명이라도 거절→ REJECTED (즉시 RESUME: rejections)
       └─원본 변경(dataVersion↑)→ STALE (RESUME: STALE)
```

- 저장(`POST /internal/plans`) 직전에 한 번 더 검증한다(검증 게이트). 위반이 있으면 422 `HARD_VIOLATION`.
- 확정(`commit`) 검사 순서: 계획안 존재 → **STALE 여부**(409 `STALE_PLAN`) → **전원 승인 여부**(409 `APPROVAL_REQUIRED`, `details.pendingRoles`) → 재검증(422) → 반영.
- 확정하면: 하루 계획 교체, 확정 계획 버전 = 변경안 번호, dataVersion +1, 다른 대기 중 변경안은 STALE, **Outbox에 콜시트 배포·알림 작업** 기록 → RabbitMQ Worker가 발송(실패분만 재시도).
- `Idempotency-Key`가 같은 확정·예약 요청은 처음 응답을 그대로 돌려준다.
- 예약(`/internal/bookings`): 승인된 변경안에서만. 아워플레이스 API 협의 전에는 `MANUAL_PENDING`(제작실장이 직접 예약 후 완료 처리). 자체 시설은 409 `BOOKING_NOT_NEEDED`.

## 7. 기준값 (팀 결정 사항, 바꾸면 이 표와 fixtures를 함께 고친다)

| 항목 | 값 |
| --- | --- |
| 우천 HARD 기준 | 강수 확률 60% 이상 |
| 주 근로 한도 | 52시간 |
| 휴게 | 30분 미만 대기는 휴게 아님, 연속 4시간 초과 금지 |
| 회차 남은 예산 | 400,000원 |
| 재계획 루프 한도 | 3회 (Agent Harness) |
| 도구 호출 한도 | 20회, 자동 탐색 120초 (Agent Harness) |

## 8. 기대값 (fixtures 기준, C의 단위 테스트에 그대로 쓴다)

| 상황 | 결과 |
| --- | --- |
| B2, 기본 가중치 | 27개 중 가능 5개. 원래 1안 불가(SCHEDULE.OUTDOOR_RAIN), 2안 가능(0.6146), 3안 불가 |
| 최적안 | 장소 P2 + 장비 P1 + 시간대 P2, 총점 **0.7446**, 추가 비용 0원 |
| 감독 "웃돈 OK" (location .35, equipment .30, weather .10, budget .05, time .10, distance .10) | 장소 P2 + 장비 P2 + 시간대 P2, 총점 **0.7437** |
| 동시녹음팀장 거절 → EXCLUDE_LOCATION L02 | 장소 P3 + 장비 P3 + 시간대 P1, 총점 **0.6771** |
| 1안 그대로 (P1·P1·P1) | 위반 1건 `SCHEDULE.OUTDOOR_RAIN` (source permit-hangang 3.1) |
| 장소 P3 + 장비 P1 + 시간대 P1 | 위반 `NO_FILMING_ZONE.DRONE` |
| 최적안의 필수 승인자 | PRODUCTION_MANAGER, DIRECTOR, AD1, AD2, DOP, GAFFER, ART_DIRECTOR, SOUND_LEAD, COSTUME_MAKEUP (9명) |
