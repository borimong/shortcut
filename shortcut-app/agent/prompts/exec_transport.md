# 할 일: 이동 수단 실행
가상 차량 업체에서 오전 촬영지에서 확정 장소까지 인원과 장비를 옮길 차량을 예약하세요. 장소 예약은 앞 단계에서 끝났습니다.
순서:
1. transport_quote로 견적을 받습니다. dest_location_id는 확정 장소 id, start는 확정 시작 시각, headcount는 사실 정보의 headcount, equipment_ids는 확정 장비 id입니다.
2. 결과의 recommended(차량 종류와 대수)와 departAt, pickup으로 transport_book을 부릅니다. 특별한 이유가 없으면 추천안을 씁니다.
3. 견적 결과의 bookings에 확정 장소가 아닌 곳으로 가는 BOOKED 예약이 남아 있으면 transport_cancel로 취소합니다.

## 지시서
$order

## 사실 정보
$facts

## 앞 단계 결과
$prior

## 사용자 수정 요청
$comment
