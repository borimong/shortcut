# 할 일: 하드 제약 근거 수집
재계획에서 지켜야 할 하드 제약 7개 범주(CONTRACT, SCHEDULE, LAW, BUDGET, NO_FLY_ZONE, DISASTER, WEATHER)마다 원문 근거를 검색하세요.
범주마다 찾을 곳은 다음과 같습니다. 범주 하나에 검색 한 번이면 충분합니다.
- CONTRACT, SCHEDULE: search_contract_clause로 아래 계약서 ID 안에서 촬영 시간, 야간 촬영 조항
- LAW: search_regulation, doc_types ["LAW", "PERMIT"]로 주 52시간과 촬영 허가 시간
- BUDGET: search_regulation, doc_types ["POLICY"]로 블록 예산 상한
- NO_FLY_ZONE: search_regulation, doc_types ["NO_FLY"]로 비행금지구역과 드론
- DISASTER, WEATHER: search_regulation, doc_types ["SAFETY"]로 재난 문자 기준과 강수량 기준
질의는 짧고 구체적으로 씁니다. 예: "주 52시간 연장 근로 한도", "시간당 강수량 야외 촬영 제외 기준".
아래 "근거가 부족했던 범주"가 있으면 그 범주만 검색하고, 이미 찾은 범주는 다시 검색하지 않습니다.
근거가 모였으면 도구를 더 부르지 말고 끝내세요.

## 변경 이벤트
$event

## 대상 배우 계약서 ID
$contracts

## 영향 분석에서 나온 위험
$risks

## 재난 문자
$alerts

## 이전 검색에서 근거가 부족했던 범주
$missing
