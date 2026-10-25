# 할 일: 촬영 허가 실행
가상 허가 기관에서 확정 장소와 시간대의 촬영 허가를 받으세요. 장소 예약은 앞 단계에서 끝났습니다.
순서:
1. permit_check_requirement로 허가가 필요한지 확인합니다. drone에는 사실 정보의 drone 값을 넣습니다.
2. required가 false면 신청하지 않고 끝냅니다.
3. kinds에 있는 종류(LOCATION, DRONE)마다 permit_apply로 신청합니다. 이미 APPROVED인 같은 종류가 permits에 있으면 다시 신청하지 않습니다.
4. 반려(DENIED)되면 사유를 확인하고 멈춥니다. 시간대나 장소를 바꿔 다시 신청하지 않습니다.

## 지시서
$order

## 사실 정보
$facts

## 앞 단계 결과
$prior

## 사용자 수정 요청
$comment
