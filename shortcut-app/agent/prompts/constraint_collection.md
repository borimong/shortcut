# 할 일: 하드 제약 근거 수집
재계획에서 지켜야 할 하드 제약 7개 범주(CONTRACT, SCHEDULE, LAW, BUDGET, NO_FLY_ZONE, DISASTER, WEATHER)마다 원문 근거를 검색하세요.
첫 응답에서 아래 검색을 한꺼번에 모두 부르세요. 범주마다 근거가 따로 필요하므로 하나도 빼지 않습니다.
1. CONTRACT, SCHEDULE: 아래 계약서 ID마다 search_contract_clause로 촬영 시간과 야간 촬영 조항
2. LAW: search_regulation, doc_types ["LAW"]로 주 52시간과 이번 변경에 걸리는 법령
3. BUDGET: search_regulation, doc_types ["POLICY"]로 블록 예산 상한
4. DISASTER, WEATHER: search_regulation, doc_types ["SAFETY"]로 재난 문자 기준과 이번 변경의 기상 조건 기준
5. 장소 허가 조건(LAW, SCHEDULE): 후보 장소마다 search_regulation, doc_types ["PERMIT"]로 "<장소 이름> 촬영 허가 시간"
6. NO_FLY_ZONE: 후보 장소마다 search_regulation, doc_types ["NO_FLY", "PERMIT"]로 "<장소 이름> 드론 비행"
허가 조건과 비행 금지 구역은 장소마다 다르므로 5, 6번 질의에는 후보 장소 이름을 그대로 넣습니다.
질의는 짧고 구체적으로 씁니다. 예: "주 52시간 연장 근로 한도", "시간당 강수량 야외 촬영 제외 기준".
아래 "근거가 부족했던 범주"가 있으면 그 범주에 해당하는 검색만 다시 하고, 이미 찾은 범주는 다시 검색하지 않습니다.
근거가 모였으면 도구를 더 부르지 말고 끝내세요.

## 변경 이벤트
$event

## 대상 배우 계약서 ID
$contracts

## 후보 장소 (현재 확정안과 1/2/3안)
$places

## 영향 분석에서 나온 위험
$risks

## 재난 문자
$alerts

## 이전 검색에서 근거가 부족했던 범주
$missing
