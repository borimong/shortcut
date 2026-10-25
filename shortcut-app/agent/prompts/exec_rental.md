# 할 일: 장비 렌탈 실행
가상 렌탈사에서 확정안의 장비 묶음을 확보하세요.
순서:
1. rental_quote로 확정 장비(equipment의 id)를 확정 시간대 기준으로 견적 받습니다. 결과의 items에서 owned가 true인 장비는 보유 장비라 빌리지 않아도 됩니다.
2. 빌려야 할 장비(owned가 false)가 있으면 그 장비 id만 rental_book으로 예약합니다. 모두 보유 장비면 예약하지 않습니다.
3. 견적 결과의 bookings에 확정안에 없는 장비의 BOOKED 렌탈이 남아 있으면 rental_cancel로 취소합니다.
확정안에 없는 장비를 빌리지 않습니다.

## 지시서
$order

## 사실 정보
$facts

## 앞 단계 결과
$prior

## 사용자 수정 요청
$comment
