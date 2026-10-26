# RAG 검색 평가: baseline

정답셋 `evals/rag_golden.json` 기준. 규정 검색은 k=8, 계약서 검색은 k=5로 받아 순위를 매겼다(Agent 기본 k=4).
Hit@1은 1등이 정답인 비율, Hit@4는 Agent가 실제로 받는 4개 안에 정답이 있는 비율, MRR은 정답 순위의 역수 평균이다.

- 떠 있는 색인: 임베딩 text-embedding-3-small (1536차원), 문서 8건, 조각 34개

## 전체 지표

| 구성 | Hit@1 | Hit@3 | Hit@4 | MRR | k 안에 정답 없음 | 범위 위반 | 오류 거부 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| live (떠 있는 rag-mcp) | 0.778 | 0.889 | 0.889 | 0.834 | 4/63 | 0 | 1/1 | 155.4 | 220.1 |
| hash-256 (개발용) | 0.476 | 0.667 | 0.746 | 0.605 | 7/63 | 0 | 1/1 | - | - |
| 3-small, 제목 붙임 (운영 설정) | 0.778 | 0.889 | 0.889 | 0.834 | 4/63 | 0 | 1/1 | - | - |
| 3-small, 본문만 | 0.794 | 0.905 | 0.937 | 0.855 | 3/63 | 0 | 1/1 | - | - |
| 3-large, 제목 붙임 | 0.921 | 0.952 | 0.952 | 0.943 | 1/63 | 0 | 1/1 | - | - |
| BM25 (글자 2개 단위) | 0.825 | 0.968 | 0.984 | 0.89 | 1/63 | 0 | 1/1 | - | - |
| 하이브리드 RRF (3-small + BM25) | 0.841 | 0.937 | 0.952 | 0.899 | 1/63 | 0 | 1/1 | - | - |

## 질의 유형별 Hit@1

| 구성 | keyword (n=14) | paraphrase (n=15) | scenario (n=8) | confusable (n=9) | filter (n=6) | contract (n=11) |
|---|---|---|---|---|---|---|
| live (떠 있는 rag-mcp) | 0.857 | 0.4 | 1.0 | 0.778 | 1.0 | 0.909 |
| hash-256 (개발용) | 0.571 | 0.267 | 0.5 | 0.444 | 0.667 | 0.545 |
| 3-small, 제목 붙임 (운영 설정) | 0.857 | 0.4 | 1.0 | 0.778 | 1.0 | 0.909 |
| 3-small, 본문만 | 0.857 | 0.467 | 1.0 | 0.778 | 1.0 | 0.909 |
| 3-large, 제목 붙임 | 1.0 | 0.8 | 1.0 | 0.889 | 0.833 | 1.0 |
| BM25 (글자 2개 단위) | 0.929 | 0.6 | 1.0 | 0.778 | 0.833 | 0.909 |
| 하이브리드 RRF (3-small + BM25) | 0.929 | 0.6 | 1.0 | 0.778 | 1.0 | 0.909 |

## 답 없는 질의와 점수 기준선

- live (떠 있는 rag-mcp): 맞힌 1등 점수 0.2527~0.8692 (중앙값 0.539), 답 없는 질의의 1등 점수 0.2156~0.5358 (중앙값 0.396)
  - 가장 균형 잡힌 기준선 0.51: 맞는 결과 63% 유지, 답 없는 질의 75% 걸러냄
- 3-small, 제목 붙임 (운영 설정): 맞힌 1등 점수 0.2537~0.8694 (중앙값 0.539), 답 없는 질의의 1등 점수 0.2155~0.5356 (중앙값 0.396)
  - 가장 균형 잡힌 기준선 0.51: 맞는 결과 63% 유지, 답 없는 질의 75% 걸러냄
- 3-small, 본문만: 맞힌 1등 점수 0.2562~0.7486 (중앙값 0.548), 답 없는 질의의 1등 점수 0.2599~0.5782 (중앙값 0.388)
  - 가장 균형 잡힌 기준선 0.46: 맞는 결과 76% 유지, 답 없는 질의 62% 걸러냄
- 3-large, 제목 붙임: 맞힌 1등 점수 0.2964~0.8089 (중앙값 0.556), 답 없는 질의의 1등 점수 0.2767~0.5945 (중앙값 0.418)
  - 가장 균형 잡힌 기준선 0.43: 맞는 결과 88% 유지, 답 없는 질의 75% 걸러냄

## live에서 1등을 놓친 질의 (14건)

| id | 유형 | 질의 | 정답 | 정답 순위 | 실제 상위 3개 |
|---|---|---|---|---|---|
| R04 | keyword | 장소 변경 시 필수 승인자 | budget-approval-policy#2 | 2 | budget-approval-policy#3(0.4335), budget-approval-policy#2(0.4171), budget-approval-policy#0(0.3073) |
| R05 | paraphrase | 시간대만 바뀌면 누구 승인을 받아야 하나요 | budget-approval-policy#2 | 2 | budget-approval-policy#3(0.424), budget-approval-policy#2(0.3573), no-fly-zone-notice#1(0.3002) |
| R08 | paraphrase | 한 명이라도 반대하면 어떻게 돼? | budget-approval-policy#3 | 없음 | law-labor-standards#2(0.1787), law-labor-standards#1(0.1743), safety-disaster-weather#3(0.1589) |
| R11 | paraphrase | 하루에 법적으로 몇 시간까지 일할 수 있어? | law-labor-standards#1 | 3 | law-labor-standards#2(0.5239), law-labor-standards#5(0.5102), law-labor-standards#1(0.4887) |
| R13 | paraphrase | 이번 주에 벌써 45시간 일했는데 촬영 하루 더 잡아도 돼? | law-labor-standards#2 | 3 | safety-disaster-weather#2(0.4931), permit-hangang-filming#1(0.4396), law-labor-standards#2(0.4249) |
| R16 | paraphrase | 드라마 촬영 현장은 52시간제 예외 아니야? | law-labor-standards#3 | 없음 | safety-disaster-weather#2(0.4504), no-fly-zone-notice#3(0.4301), permit-hangang-filming#3(0.3943) |
| R18 | paraphrase | 8시간 촬영하면 쉬는 시간은 얼마나 줘야 해? | law-labor-standards#4 | 5 | permit-hangang-filming#1(0.4563), safety-disaster-weather#2(0.4279), permit-hangang-filming#3(0.4034) |
| R19 | keyword | 야간근로 가산 수당 | law-labor-standards#5 | 7 | no-fly-zone-notice#2(0.2853), no-fly-zone-notice#1(0.2685), safety-disaster-weather#1(0.2653) |
| R21 | confusable | 22시 이후 촬영 제한 | law-labor-standards#5 | 없음 | safety-disaster-weather#2(0.5181), no-fly-zone-notice#0(0.4604), permit-hangang-filming#1(0.4582) |
| R23 | paraphrase | 허가 없이 드론 띄우면 어떻게 돼? | no-fly-zone-notice#1 | 3 | permit-hangang-filming#3(0.2836), no-fly-zone-notice#3(0.2785), no-fly-zone-notice#1(0.2779) |
| R26 | paraphrase | 북한 가까운 데서 드론 촬영 가능해? | no-fly-zone-notice#2 | 없음 | permit-hangang-filming#3(0.495), permit-hangang-filming#2(0.463), no-fly-zone-notice#3(0.452) |
| R35 | paraphrase | 한강에서 확성기 얼마나 오래 써도 돼? | permit-hangang-filming#3 | 2 | permit-hangang-filming#1(0.3983), permit-hangang-filming#3(0.3458), permit-hangang-filming#2(0.312) |
| R43 | confusable | 우천 시 실내 장소로 바꾸면 비 영향이 있나 | safety-disaster-weather#2 | 5 | no-fly-zone-notice#3(0.3049), budget-approval-policy#0(0.2625), no-fly-zone-notice#2(0.2497) |
| C11 | contract | 쉬는 시간 | contract-actor-c-v2#2 | 2 | contract-actor-c-v2#1(0.301), contract-actor-c-v2#2(0.2552), contract-actor-c-v2#0(0.1454) |

## live에서 답 없는 질의의 결과

| id | 질의 | 상위 3개 |
|---|---|---|
| N01 | 소품 대여 보험 가입 의무 | budget-approval-policy#3(0.2607), budget-approval-policy#2(0.258), budget-approval-policy#1(0.2479) |
| N02 | 촬영장 주차 요금 정산 방법 | budget-approval-policy#1(0.5088), safety-disaster-weather#2(0.4557), permit-hangang-filming#2(0.4393) |
| N03 | 아역 배우 촬영 시간 제한 | safety-disaster-weather#2(0.5357), no-fly-zone-notice#0(0.5019), no-fly-zone-notice#3(0.4998) |
| N04 | 케이터링 식대 1인당 한도 | no-fly-zone-notice#0(0.2156), budget-approval-policy#2(0.2146), law-labor-standards#2(0.1958) |
| N05 | 배경 음악 저작권 사용 허락 | permit-hangang-filming#0(0.3465), permit-hangang-filming#3(0.341), budget-approval-policy#1(0.3216) |
| N06 | 부산 해운대 촬영 허가 조건 | permit-hangang-filming#0(0.5358), permit-hangang-filming#1(0.5216), permit-hangang-filming#2(0.5101) |
| N07 | 미세먼지 나쁨일 때 야외 촬영 | safety-disaster-weather#2(0.4455), budget-approval-policy#1(0.3701), permit-hangang-filming#2(0.3662) |
| N08 | 스태프 숙소 배정 기준 | safety-disaster-weather#2(0.302), no-fly-zone-notice#0(0.2824), budget-approval-policy#0(0.2723) |
