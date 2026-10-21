# 평가 결과: v3_actual

| scenario | ok | status | finalLocation | loops | toolCalls | llmCalls | tokens | costUsd | latencyMs | retries | fallbacks | evidenceCoverage | reviewRounds | reviewScore | hardViolationPassed | failedChecks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v3_noise_approve | True | DONE | 모노스튜디오 사무실 세트 | 1 | 19 | 11 | 31761 | 0.005868 | 35599 | 0 | 0 | 5/7 | 1 | 85 | False | [] |
| v3_noise_reject_sound | True | DONE | 하루오피스 복합 세트 | 2 | 22 | 14 | 39745 | 0.007361 | 40299 | 0 | 0 | 5/7 | 1 | 85 | False | [] |
| v3_premium_instruction | True | DONE | 하루오피스 복합 세트 | 1 | 19 | 12 | 33146 | 0.00618 | 32833 | 0 | 0 | 5/7 | 1 | 81 | False | [] |
| v3_camera_failure | True | DONE | 새봄스튜디오 사무실 세트 | 1 | 19 | 11 | 32008 | 0.005988 | 32102 | 0 | 0 | 5/7 | 1 | 85 | False | [] |
| v3_equipment_reject_director | False | FAILED | 모노스튜디오 사무실 세트 | None | None | None | None | None | None | None | None | 5/7 | 1 | 85 | None | ['1:UNCHANGED_EQUIPMENT', '1:HAS_EQUIPMENT_1', '1:MISSING_APPROVER_DOP'] |
| v3_cost_reject_producer | False | FAILED | 모노스튜디오 사무실 세트 | None | None | None | None | None | None | None | None | 5/7 | 1 | 85 | None | [] |
| v3_main_replan | False | DONE | 하루오피스 복합 세트 | 2 | 22 | 15 | 43658 | 0.007953 | 41816 | 0 | 0 | 5/7 | 1 | 81 | False | ['QA1:NO_SOURCES'] |
| v3_rain_after_exteriors | True | DONE | 새봄스튜디오 사무실 세트 | 1 | 19 | 12 | 36109 | 0.006652 | 35294 | 0 | 0 | 5/7 | 1 | 85 | False | [] |
| v3_no_interiors | True | NEEDS_HUMAN | None | 1 | 17 | 11 | 32245 | 0.005787 | 29565 | 0 | 0 | None | None | None | None | [] |

- 기대 결과 일치: 6/9
- 하드 제약 위반안 확정 건수: 0
