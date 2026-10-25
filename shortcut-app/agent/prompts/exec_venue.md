# 할 일: 장소 예약 실행
가상 아워플레이스에서 확정 장소를 확정 시간대로 예약 확정하세요.
순서:
1. venue_check로 확정 장소의 가용 여부와 이 촬영일의 기존 예약(reservations)을 확인합니다.
2. 확정 장소, 확정 시간대에 이미 CONFIRMED 예약이 있으면 새로 잡지 않습니다.
3. 없으면 venue_hold로 가예약한 뒤, 받은 reservationId로 venue_confirm을 불러 확정합니다.
4. 이 촬영일에 더는 쓰지 않는 이전 장소(originalLocation)의 예약이 HELD나 CONFIRMED로 남아 있으면 venue_cancel로 취소합니다. 확정 장소 예약은 취소하지 않습니다.
5. 가용하지 않거나 가예약이 거부되면 다른 장소나 다른 시간으로 바꾸지 말고 멈춥니다.
task_id와 shoot_day_id는 사실 정보의 taskId, shootDayId를 씁니다.

## 지시서
$order

## 사실 정보
$facts

## 앞 단계 결과
$prior

## 사용자 수정 요청
$comment
