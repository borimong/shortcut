# 제약 수집 근거 인용 평가 (main1026)

- 코퍼스: full, 문서 62개, 조항 347개
- 시나리오 150개, 범주 판정 1050건, 인용 1414건
- 모델 gpt-4o-mini, 대체 gpt-4.1-mini, 임베딩 text-embedding-3-small
- 실행 횟수 분포(라운드 수: 시나리오 수) {2: 150}, 평균 도구 호출 25.13회, 평균 34.4초, 비용 $0.934

## 인용 정확도

- 인용 정밀도(관대): 0.988
- 인용 정밀도(엄격, 상황까지 맞아야 정답): 0.761
- 틀린 인용 원인: {'content': 17} (scope: 범주는 맞지만 다른 배우나 장소, 옛 버전 / content: 그 범주 내용이 아님)
- 틀린 인용 범주: {'WEATHER': 11, 'DISASTER': 4, 'SCHEDULE': 1, 'CONTRACT': 1}
- 모델이 적었지만 검색한 적 없어 코드가 버린 ID: 9건

## 범주 판정 결과 (관대 기준)

clean: 인용 전부 정답 / mixed: 정답과 오답 섞임 / false_cover: 인용이 있지만 전부 오답(근거 있음으로 잘못 통과) / missed_llm: 정답이 검색됐는데 인용 안 함 / missed_retrieval: 정답이 검색되지 않음 / true_missing: 정답이 없어 비운 것

| 범주 | clean | mixed | false_cover | missed_llm | missed_retrieval | true_missing |
|---|---|---|---|---|---|---|
| CONTRACT | 149 | 1 | 0 | 0 | 0 | 0 |
| SCHEDULE | 149 | 1 | 0 | 0 | 0 | 0 |
| LAW | 150 | 0 | 0 | 0 | 0 | 0 |
| BUDGET | 150 | 0 | 0 | 0 | 0 | 0 |
| NO_FLY_ZONE | 142 | 0 | 0 | 1 | 7 | 0 |
| DISASTER | 146 | 3 | 1 | 0 | 0 | 0 |
| WEATHER | 139 | 9 | 2 | 0 | 0 | 0 |
| 전체 | 1025 | 14 | 3 | 1 | 7 | 0 |

엄격 기준 전체: {'clean': 736, 'mixed': 111, 'false_cover': 195, 'missed_retrieval': 8}

## 노드의 문서 종류 규칙(EVIDENCE_TYPES)

- 모델 인용에서 실제로 지운 것: 오답 5건, 정답 0건
- 남은 인용 가운데 규칙에 걸리는 것(0이어야 함): 오답 0건, 정답 0건

## 틀린 인용 예시

| 시나리오 | 범주 | 조항 | 문서 종류 | 원인 | 규칙 통과 |
|---|---|---|---|---|---|
| s004-cold | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s005-wind | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s010-actor_unavailable | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s019-heavy_rain_alert | DISASTER | permit-hangang-filming#2 기상 악화 시 안전 조치 | PERMIT | content | 예 |
| s021-cold | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s033-drone_add | SCHEDULE | contract-actor-l-v1#4 제6조 동물 복지 | CONTRACT | content | 예 |
| s083-heat | DISASTER | permit-seoul-forest-filming#3 기상 악화 시 조치 | PERMIT | content | 예 |
| s102-heavy_rain_alert | DISASTER | safety-disaster-weather#2 강수량에 따른 야외 촬영 판단 | SAFETY | content | 예 |
| s103-heat | DISASTER | permit-hangang-filming#2 기상 악화 시 안전 조치 | PERMIT | content | 예 |
| s104-cold | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s109-lightning | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s110-actor_unavailable | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s113-drone_add | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s117-crowd | WEATHER | permit-gwanghwamun-filming#3 인파 밀집 행사일 안전 | PERMIT | content | 예 |
| s129-lightning | WEATHER | safety-disaster-weather#1 긴급재난문자 수신 시 원칙 | SAFETY | content | 예 |
| s137-crowd | CONTRACT | contract-actor-d-v1#6 제12조 초상권과 홍보 활동 | CONTRACT | content | 예 |
| s146-typhoon | WEATHER | permit-gwanghwamun-filming#3 인파 밀집 행사일 안전 | PERMIT | content | 예 |
