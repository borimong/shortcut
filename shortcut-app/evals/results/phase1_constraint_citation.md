# 제약 수집 근거 인용 평가 (full)

- 코퍼스: full, 문서 62개, 조항 347개
- 시나리오 150개, 범주 판정 1050건, 인용 1191건
- 모델 gpt-4o-mini, 대체 gpt-4.1-mini, 임베딩 text-embedding-3-small
- 실행 횟수 분포(라운드 수: 시나리오 수) {1: 130, 2: 20}, 평균 도구 호출 9.64회, 평균 17.7초, 비용 $0.4352

## 인용 정확도

- 인용 정밀도(관대): 0.8774
- 인용 정밀도(엄격, 상황까지 맞아야 정답): 0.7448
- 틀린 인용 원인: {'scope': 115, 'content': 31} (scope: 범주는 맞지만 다른 배우나 장소, 옛 버전 / content: 그 범주 내용이 아님)
- 틀린 인용 범주: {'NO_FLY_ZONE': 100, 'SCHEDULE': 33, 'DISASTER': 7, 'LAW': 6}
- 모델이 적었지만 검색한 적 없어 코드가 버린 ID: 6건

## 범주 판정 결과 (관대 기준)

clean: 인용 전부 정답 / mixed: 정답과 오답 섞임 / false_cover: 인용이 있지만 전부 오답(근거 있음으로 잘못 통과) / missed_llm: 정답이 검색됐는데 인용 안 함 / missed_retrieval: 정답이 검색되지 않음 / true_missing: 정답이 없어 비운 것

| 범주 | clean | mixed | false_cover | missed_llm | missed_retrieval | true_missing |
|---|---|---|---|---|---|---|
| CONTRACT | 150 | 0 | 0 | 0 | 0 | 0 |
| SCHEDULE | 115 | 4 | 20 | 11 | 0 | 0 |
| LAW | 142 | 0 | 5 | 3 | 0 | 0 |
| BUDGET | 150 | 0 | 0 | 0 | 0 | 0 |
| NO_FLY_ZONE | 49 | 0 | 100 | 1 | 0 | 0 |
| DISASTER | 143 | 2 | 5 | 0 | 0 | 0 |
| WEATHER | 150 | 0 | 0 | 0 | 0 | 0 |
| 전체 | 899 | 6 | 130 | 15 | 0 | 0 |

엄격 기준 전체: {'clean': 743, 'false_cover': 267, 'missed_llm': 15, 'mixed': 25}

## 1단계(문서 종류 규칙)를 적용했다면

- 지워지는 오답 인용 39건, 함께 지워지는 정답 인용 0건
- 적용 후 범주 판정 전체: {'clean': 904, 'false_cover': 105, 'missed_llm': 40, 'mixed': 1}

## 틀린 인용 예시

| 시나리오 | 범주 | 조항 | 문서 종류 | 원인 | 규칙 통과 |
|---|---|---|---|---|---|
| s001-rain | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s002-heavy_rain_alert | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s003-heat | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s004-cold | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s006-typhoon | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s007-earthquake | SCHEDULE | permit-seoul-forest-filming#1 허가 시간 | PERMIT | scope | 아니오 |
| s008-dust | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s009-lightning | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s010-actor_unavailable | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s010-actor_unavailable | DISASTER | permit-haeundae-filming#4 태풍과 해일 | PERMIT | scope | 아니오 |
| s011-night_extension | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s012-equipment | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s013-drone_add | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s014-location_cancel | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s014-location_cancel | DISASTER | permit-haeundae-filming#4 태풍과 해일 | PERMIT | scope | 아니오 |
| s015-budget_cut | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s016-overtime | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s016-overtime | DISASTER | permit-haeundae-filming#4 태풍과 해일 | PERMIT | scope | 아니오 |
| s017-crowd | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s018-rain | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s019-heavy_rain_alert | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s020-heat | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s021-cold | NO_FLY_ZONE | no-fly-zone-notice#0 개요 | NO_FLY | content | 예 |
| s022-wind | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s023-typhoon | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s024-earthquake | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s025-dust | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s026-lightning | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s027-actor_unavailable | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s028-night_extension | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s029-equipment | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s030-drone_add | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s030-drone_add | DISASTER | permit-haeundae-filming#4 태풍과 해일 | PERMIT | scope | 아니오 |
| s032-equipment | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s037-crowd | NO_FLY_ZONE | no-fly-zone-notice#2 휴전선 인근 비행금지구역 | NO_FLY | scope | 예 |
| s038-water | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s039-stunt | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s040-minor_late | SCHEDULE | law-labor-minor-workers#3 제69조 근로시간 | LAW | content | 아니오 |
| s040-minor_late | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
| s041-rain | NO_FLY_ZONE | nofly-p73-seoul#1 구역 범위 | NO_FLY | scope | 예 |
