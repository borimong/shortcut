# 할 일: 제작비 장부 실행
이번 변경으로 생긴 비용을 장부에 기록하세요. 금액은 서버가 예약 번호로 직접 찾아 넣으므로 금액을 쓰지 않습니다.
순서:
1. 아래 "기록할 수 있는 번호"에 있는 항목만 기록합니다. 목록에 없는 번호는 지어내지 않습니다.
   앞 단계에서 실행하지 않은 Agent(예: 렌탈을 건너뜀)는 비용이 생기지 않았으므로 그 계정은 기록하지 않습니다.
   계정과 ref_type은 목록에 적힌 값을 그대로 씁니다. 참고로 각 번호의 출처는 다음과 같습니다.
   - 장소 예약 reservationId: account VENUE, ref_type RESERVATION
   - 렌탈 bookingId: account EQUIPMENT_RENTAL, ref_type RENTAL
   - 차량 bookingId: account TRANSPORT, ref_type TRANSPORT
   - 허가 permitId(APPROVED): account PERMIT_FEE, ref_type PERMIT
   - 취소한 예약(cancelled 목록): account CANCEL_FEE, ref_type은 원래 예약 종류
2. ledger_record 한 번에 모두 기록합니다. memo에는 무엇 때문에 쓴 돈인지 한 문장으로 씁니다(예: "우천으로 한강 공원에서 성수 스튜디오로 장소 변경, 오후 대관료").
3. ledger_budget_status로 블록 예산 대비 집행을 확인합니다. over가 true면 보고에 초과 사유를 씁니다.

## 기록할 수 있는 번호
$refs

## 지시서
$order

## 사실 정보
$facts

## 앞 단계 결과
$prior

## 사용자 수정 요청
$comment
