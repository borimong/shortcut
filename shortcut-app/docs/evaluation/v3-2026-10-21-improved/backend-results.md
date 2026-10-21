# V3 실제 DB·백엔드 평가

통과: 11/11

Agent/LLM 평가 결과가 아닙니다. API 키 미설정으로 Agent 9개 시나리오는 미실행입니다.

| 검사 | 결과 | 상세 |
|---|---|---|
| V3 실제 시드·콜시트 연결 | PASS | {"scenes": 24, "date": "2026-10-23", "fixedScenes": 8, "changingScenes": 16} |
| 소음 시 LOC-STUDIO 대체 | PASS | {"location": "모노스튜디오 사무실 세트", "locationId": 4, "equipmentIds": [1, 4, 7, 10, 12], "cost": 180000, "feasibleCount": 15} |
| 장소 제외 제약 적용 시 LOC-HUB 대체 | PASS | {"location": "하루오피스 복합 세트", "locationId": 6, "equipmentIds": [1, 4, 7, 10, 12], "cost": 450000, "feasibleCount": 6} |
| 카메라 고장 시 실제 CAM-B 선택 | PASS | {"location": "새봄스튜디오 사무실 세트", "locationId": 2, "equipmentIds": [2, 4, 7, 10, 12], "cost": 160000, "feasibleCount": 6} |
| 카메라 A 제외 제약 적용 | PASS | {"location": "모노스튜디오 사무실 세트", "locationId": 4, "equipmentIds": [2, 4, 7, 10, 12], "cost": 340000, "feasibleCount": 3} |
| 추가비 10만원 제한 시 후보 없음 | PASS | {"feasibleCount": 0} |
| 실내 세 곳 사용 불가 시 후보 없음 | PASS | {"feasibleCount": 0} |
| 야외 완료 후 비 예보 시 기존 실내 유지 | PASS | {"location": "새봄스튜디오 사무실 세트", "locationId": 2, "equipmentIds": [1, 4, 7, 10, 12], "cost": 0, "feasibleCount": 24} |
| 금지 장소·비호환 음향·시간 이탈 차단 | PASS | {"rejectedViolationCodes": [["V3_INTERIOR_SCOPE"], ["EQUIPMENT_UNAVAILABLE", "V3_EQUIPMENT_GROUPS"], ["V3_FIXED_PM_WINDOW"]]} |
| 사건 초기화·가용 상태 복원 | PASS | {"equipmentRestored": true, "locationRestored": true} |
| 카메라와 24씬 영향 관계 연결 | PASS | {"impactedScenes": 24} |
