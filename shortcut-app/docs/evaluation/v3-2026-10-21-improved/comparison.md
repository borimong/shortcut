# 평가 비교: v3_actual vs v3_improved_20aff19

| scenario | ok (v3_actual -> v3_improved_20aff19) | status (v3_actual -> v3_improved_20aff19) | loops (v3_actual -> v3_improved_20aff19) | toolCalls (v3_actual -> v3_improved_20aff19) | llmCalls (v3_actual -> v3_improved_20aff19) | tokens (v3_actual -> v3_improved_20aff19) | costUsd (v3_actual -> v3_improved_20aff19) | latencyMs (v3_actual -> v3_improved_20aff19) | evidenceCoverage (v3_actual -> v3_improved_20aff19) |
|---|---|---|---|---|---|---|---|---|---|
| v3_noise_approve | True -> True | DONE -> DONE | 1 -> 1 | 19 -> 19 | 11 -> 12 | 31761 -> 36102 | 0.005868 -> 0.006552 | 35599 -> 38395 | 5/7 -> 5/7 |
| v3_noise_reject_sound | True -> True | DONE -> DONE | 2 -> 2 | 22 -> 23 | 14 -> 15 | 39745 -> 42740 | 0.007361 -> 0.007864 | 40299 -> 40429 | 5/7 -> 5/7 |
| v3_premium_instruction | True -> True | DONE -> DONE | 1 -> 1 | 19 -> 19 | 12 -> 12 | 33146 -> 33301 | 0.00618 -> 0.006163 | 32833 -> 32334 | 5/7 -> 5/7 |
| v3_camera_failure | True -> True | DONE -> DONE | 1 -> 1 | 19 -> 18 | 11 -> 11 | 32008 -> 31396 | 0.005988 -> 0.00585 | 32102 -> 30854 | 5/7 -> 5/7 |
| v3_equipment_reject_director | False -> True | FAILED -> DONE | None -> 2 | None -> 22 | None -> 14 | None -> 42592 | None -> 0.007736 | None -> 35832 | 5/7 -> 5/7 |
| v3_cost_reject_producer | False -> True | FAILED -> NEEDS_HUMAN | None -> 2 | None -> 20 | None -> 12 | None -> 34892 | None -> 0.006401 | None -> 32166 | 5/7 -> 5/7 |
| v3_main_replan | False -> True | DONE -> DONE | 2 -> 2 | 22 -> 23 | 15 -> 16 | 43658 -> 46976 | 0.007953 -> 0.008448 | 41816 -> 39092 | 5/7 -> 5/7 |
| v3_rain_after_exteriors | True -> True | DONE -> DONE | 1 -> 1 | 19 -> 19 | 12 -> 12 | 36109 -> 36562 | 0.006652 -> 0.006711 | 35294 -> 31749 | 5/7 -> 5/7 |
| v3_no_interiors | True -> True | NEEDS_HUMAN -> NEEDS_HUMAN | 1 -> 1 | 17 -> 17 | 11 -> 11 | 32245 -> 32631 | 0.005787 -> 0.005832 | 29565 -> 27358 | None -> None |
