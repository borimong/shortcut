# RAG 검색 평가: phase2_vector

정답셋 `evals/rag_golden.json` 기준. 규정 검색은 k=8, 계약서 검색은 k=5로 받아 순위를 매겼다(Agent 기본 k=4).
Hit@1은 1등이 정답인 비율, Hit@4는 Agent가 실제로 받는 4개 안에 정답이 있는 비율, MRR은 정답 순위의 역수 평균이다.

- 떠 있는 색인: 임베딩 text-embedding-3-small (1536차원), 문서 12건, 조각 72개

## 전체 지표

| 구성 | Hit@1 | Hit@3 | Hit@4 | MRR | k 안에 정답 없음 | 범위 위반 | 오류 거부 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| live (떠 있는 rag-mcp) | 0.746 | 0.873 | 0.873 | 0.815 | 4/63 | 0 | 1/1 | 156.8 | 202.7 |

## 질의 유형별 Hit@1

| 구성 | keyword (n=14) | paraphrase (n=15) | scenario (n=8) | confusable (n=9) | filter (n=6) | contract (n=11) |
|---|---|---|---|---|---|---|
| live (떠 있는 rag-mcp) | 0.857 | 0.4 | 0.875 | 0.778 | 0.833 | 0.909 |

## 답 없는 질의와 점수 기준선

- live (떠 있는 rag-mcp): 맞힌 1등 점수 0.2527~0.8693 (중앙값 0.55), 답 없는 질의의 1등 점수 0.2155~0.5358 (중앙값 0.396)
  - 가장 균형 잡힌 기준선 0.51: 맞는 결과 66% 유지, 답 없는 질의 75% 걸러냄

## live에서 1등을 놓친 질의 (16건)

| id | 유형 | 질의 | 정답 | 정답 순위 | 실제 상위 3개 |
|---|---|---|---|---|---|
| R04 | keyword | 장소 변경 시 필수 승인자 | budget-approval-policy#2 | 2 | budget-approval-policy#3(0.4335), budget-approval-policy#2(0.4171), budget-approval-policy#0(0.3073) |
| R05 | paraphrase | 시간대만 바뀌면 누구 승인을 받아야 하나요 | budget-approval-policy#2 | 2 | budget-approval-policy#3(0.424), budget-approval-policy#2(0.3573), no-fly-zone-notice#1(0.3002) |
| R08 | paraphrase | 한 명이라도 반대하면 어떻게 돼? | budget-approval-policy#3 | 없음 | law-labor-standards#2(0.1788), law-labor-standards#1(0.175), safety-disaster-weather#3(0.1589) |
| R11 | paraphrase | 하루에 법적으로 몇 시간까지 일할 수 있어? | law-labor-standards#1 | 3 | law-labor-standards#2(0.5238), law-labor-standards#5(0.5098), law-labor-standards#1(0.4873) |
| R13 | paraphrase | 이번 주에 벌써 45시간 일했는데 촬영 하루 더 잡아도 돼? | law-labor-standards#2 | 5 | safety-disaster-weather#2(0.4928), permit-hapjeong-rooftop#1(0.4744), permit-hapjeong-rooftop#3(0.4698) |
| R14 | scenario | 재촬영 일정이 주간 누적 근로시간 52시간을 넘는지 확인 | law-labor-standards#2 | 2 | permit-hapjeong-rooftop#1(0.5381), law-labor-standards#2(0.4698), permit-hapjeong-rooftop#0(0.4523) |
| R16 | paraphrase | 드라마 촬영 현장은 52시간제 예외 아니야? | law-labor-standards#3 | 없음 | safety-disaster-weather#2(0.4502), no-fly-zone-notice#3(0.4301), permit-hapjeong-rooftop#1(0.4054) |
| R18 | paraphrase | 8시간 촬영하면 쉬는 시간은 얼마나 줘야 해? | law-labor-standards#4 | 8 | permit-hapjeong-rooftop#1(0.471), permit-hangang-filming#1(0.4563), safety-disaster-weather#2(0.428) |
| R19 | keyword | 야간근로 가산 수당 | law-labor-standards#5 | 6 | no-fly-zone-notice#2(0.2853), no-fly-zone-notice#1(0.2682), safety-disaster-weather#1(0.2651) |
| R21 | confusable | 22시 이후 촬영 제한 | law-labor-standards#5 | 없음 | safety-disaster-weather#2(0.518), permit-hapjeong-rooftop#1(0.5039), permit-hapjeong-rooftop#2(0.4655) |
| R23 | paraphrase | 허가 없이 드론 띄우면 어떻게 돼? | no-fly-zone-notice#1 | 3 | permit-hangang-filming#3(0.2836), no-fly-zone-notice#3(0.2785), no-fly-zone-notice#1(0.2779) |
| R26 | paraphrase | 북한 가까운 데서 드론 촬영 가능해? | no-fly-zone-notice#2 | 없음 | permit-hangang-filming#3(0.4951), permit-hangang-filming#2(0.4639), no-fly-zone-notice#3(0.452) |
| R35 | paraphrase | 한강에서 확성기 얼마나 오래 써도 돼? | permit-hangang-filming#3 | 2 | permit-hangang-filming#1(0.3984), permit-hangang-filming#3(0.3459), permit-hangang-filming#2(0.3109) |
| R43 | confusable | 우천 시 실내 장소로 바꾸면 비 영향이 있나 | safety-disaster-weather#2 | 5 | no-fly-zone-notice#3(0.3049), budget-approval-policy#0(0.2625), no-fly-zone-notice#2(0.2497) |
| F04 | filter | 비 예보 시 촬영 판단 | permit-hangang-filming#2 | 2 | permit-hapjeong-rooftop#3(0.4833), permit-hangang-filming#2(0.4608), permit-hapjeong-rooftop#0(0.4427) |
| C11 | contract | 쉬는 시간 | contract-actor-c-v2#2 | 2 | contract-actor-c-v2#1(0.3026), contract-actor-c-v2#2(0.2552), contract-actor-c-v2#0(0.1451) |

## live에서 답 없는 질의의 결과

| id | 질의 | 상위 3개 |
|---|---|---|
| N01 | 소품 대여 보험 가입 의무 | budget-approval-policy#3(0.2607), budget-approval-policy#2(0.258), budget-approval-policy#1(0.2479) |
| N02 | 촬영장 주차 요금 정산 방법 | budget-approval-policy#1(0.5088), safety-disaster-weather#2(0.4554), permit-hangang-filming#2(0.4405) |
| N03 | 아역 배우 촬영 시간 제한 | safety-disaster-weather#2(0.5353), permit-hapjeong-rooftop#1(0.522), no-fly-zone-notice#0(0.5019) |
| N04 | 케이터링 식대 1인당 한도 | no-fly-zone-notice#0(0.2155), budget-approval-policy#2(0.2146), law-labor-standards#2(0.1961) |
| N05 | 배경 음악 저작권 사용 허락 | permit-hangang-filming#0(0.3464), permit-hangang-filming#3(0.3409), budget-approval-policy#1(0.3216) |
| N06 | 부산 해운대 촬영 허가 조건 | permit-hangang-filming#0(0.5358), permit-hapjeong-rooftop#0(0.5262), permit-hangang-filming#1(0.5217) |
| N07 | 미세먼지 나쁨일 때 야외 촬영 | safety-disaster-weather#2(0.4453), permit-hapjeong-rooftop#3(0.4143), permit-hapjeong-rooftop#0(0.3887) |
| N08 | 스태프 숙소 배정 기준 | safety-disaster-weather#2(0.3018), no-fly-zone-notice#0(0.2824), budget-approval-policy#0(0.2723) |
