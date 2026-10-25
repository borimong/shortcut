# 할 일: 거절 사유를 보완하는 추가 제약 만들기
승인자가 변경안을 거절했습니다. 다음 루프의 새 안이 이 사유를 보완하도록, 승인자가 문제로 고른 요소만 바꾸는 추가 제약을 1~3개 만드세요.
문제로 고르지 않은 요소는 바꾸지 않습니다. 그 요소에 대한 제약은 만들지 마세요.

요소별로 쓸 수 있는 제약은 다음과 같습니다.
- 장소: 그 장소의 특정 시간대가 문제면 EXCLUDE_LOCATION_TIME(location_id, from_time, to_time), 장소 자체가 문제면 EXCLUDE_LOCATION(location_id), 실내여야 하면 REQUIRE_INDOOR, 사유가 "야외 장면은 야외에서"처럼 대본의 실내/실외를 지키라고 직접 말하면 REQUIRE_SETTING_MATCH. "장면 의도와 맞지 않는다"처럼 실내/실외를 말하지 않는 사유에는 REQUIRE_SETTING_MATCH를 쓰지 말고 그 장소를 뺍니다
- 시간대: 그 시간대를 피해야 하면 EXCLUDE_TIME(from_time, to_time), 더 일찍 끝나야 하면 LATEST_END(time)
- 장비: 문제 장비를 빼야 하면 EXCLUDE_EQUIPMENT(equipment_id). 아래 장비 목록의 id를 쓰고, 여러 개면 제약을 여러 개 만듭니다
- 비용: 추가 비용을 줄여야 하면 MAX_EXTRA_COST(amount). 사유에 금액이 없으면 거절된 안의 추가 비용보다 1원 적게 둡니다
- 기타: 사유를 읽고 위 요소 가운데 가장 가까운 것을 고릅니다

사유에 시간이 없으면 거절된 안의 시간대를 쓰고, "오후 소음"처럼 범위가 넓으면 그 범위(예: 13:00~18:00)를 씁니다.
summary에는 새 안이 무엇을 어떻게 바꿔 사유를 보완하는지 한 문장으로 씁니다.

## 거절한 승인자
$role

## 문제로 고른 요소
$issues

## 거절 사유
$reason

## 거절된 안
$plan (장소 ID $location_id, 시간 $start~$end, 추가 비용 $extra_cost원)

## 거절된 안의 장비
$equipment
