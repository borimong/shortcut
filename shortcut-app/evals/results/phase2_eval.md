# 평가 결과: main1026_a

| scenario | ok | status | finalLocation | sceneOrder | loops | toolCalls | llmCalls | tokens | costUsd | latencyMs | retries | fallbacks | evidenceCoverage | reviewRounds | reviewScore | hardViolationPassed | execStatus | execDone | execSkipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rain_approve | True | DONE | 성수 스튜디오 | S12 → S13 | 1 | 42 | 43 | 114657 | 0.021033 | 101144 | 0 | 0 | 8/8 | 2 | 95 | False | DONE | venue,rental,permit,transport,contact,ledger |  |
| rain_reject_sound | True | DONE | 일산 실내 스튜디오 | S12 → S13 | 2 | 63 | 57 | 187524 | 0.035205 | 177121 | 0 | 0 | 8/8 | 2 | 95 | False | DONE | venue,rental,permit,transport,contact,ledger |  |
| disaster_alert | True | DONE | 파주 세트장 | S12 → S13 | 1 | 40 | 36 | 100890 | 0.01845 | 85088 | 0 | 0 | 8/8 | 1 | 95 | False | DONE | venue,rental,transport,contact,ledger | permit |
| premium_instruction | True | DONE | 성수 스튜디오 | S12 → S13 | 1 | 41 | 44 | 121086 | 0.022332 | 101723 | 0 | 0 | 8/8 | 2 | 95 | False | DONE | venue,rental,permit,transport,contact,ledger |  |
| fourth_plan_after_rejections | True | DONE | 하남 카페 세트 | S12 → S13 | 3 | 52 | 75 | 274380 | 0.050951 | 242974 | 0 | 0 | 8/8 | 5 | 77 | False | DONE | venue,rental,permit,transport,contact,ledger |  |
| actor_busy_reorder | True | DONE | 성수 스튜디오 | S19 → S18 | 1 | 33 | 28 | 86444 | 0.015933 | 80609 | 0 | 0 | 8/8 | 2 | 100 | False | DONE | transport,contact,ledger | venue,rental,permit |
| exec_venue_conflict | True | NEEDS_HUMAN | 성수 스튜디오 | S12 → S13 | 1 | 27 | 21 | 72902 | 0.013801 | 70429 | 0 | 0 | 8/8 | 2 | 85 | None | NEEDS_HUMAN | rental |  |

- 기대 결과 일치: 7/7
- 하드 제약 위반안 확정 건수: 0
