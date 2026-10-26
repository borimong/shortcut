# 평가 결과: main_final

| scenario | ok | status | finalLocation | sceneOrder | loops | toolCalls | llmCalls | tokens | costUsd | latencyMs | retries | fallbacks | evidenceCoverage | reviewRounds | reviewScore | hardViolationPassed | execStatus | execDone | execSkipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rain_approve | True | DONE | 성수 스튜디오 | S12 → S13 | 1 | 56 | 43 | 128362 | 0.024047 | 125187 | 0 | 0 | 8/8 | 2 | 83 | False | DONE | venue,permit,transport,contact,ledger | rental |
| rain_reject_sound | True | DONE | 상암 호리존 스튜디오 | S12 → S13 | 2 | 62 | 56 | 185223 | 0.034934 | 182169 | 0 | 0 | 8/8 | 4 | 95 | False | DONE | venue,permit,transport,contact,ledger | rental |
| disaster_alert | True | DONE | 파주 세트장 | S12 → S13 | 1 | 39 | 34 | 91123 | 0.016694 | 75562 | 0 | 0 | 8/8 | 1 | 93 | False | DONE | venue,rental,transport,contact,ledger | permit |
| premium_instruction | True | DONE | 성수 스튜디오 | S12 → S13 | 1 | 41 | 44 | 121014 | 0.022323 | 98955 | 0 | 0 | 8/8 | 2 | 95 | False | DONE | venue,rental,permit,transport,contact,ledger |  |
| fourth_plan_after_rejections | True | DONE | 하남 카페 세트 | S12 → S13 | 3 | 67 | 68 | 251951 | 0.047467 | 233481 | 0 | 0 | 8/8 | 4 | 85 | False | DONE | venue,rental,transport,contact,ledger | permit |
| actor_busy_reorder | True | DONE | 성수 스튜디오 | S19 → S18 | 1 | 34 | 26 | 75107 | 0.014121 | 77251 | 0 | 0 | 8/8 | 2 | 100 | False | DONE | transport,contact,ledger | venue,rental,permit |
| exec_venue_conflict | True | NEEDS_HUMAN | 성수 스튜디오 | S12 → S13 | 1 | 43 | 22 | 84641 | 0.01619 | 89268 | 0 | 0 | 7/8 | 2 | 87 | None | NEEDS_HUMAN |  | rental |

- 기대 결과 일치: 7/7
- 하드 제약 위반안 확정 건수: 0
