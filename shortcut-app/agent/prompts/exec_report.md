# 할 일: 실행 보고 작성
$agent Agent의 실행 결과를 supervisor와 사용자가 읽을 보고로 정리하세요.
- 성공 여부(status)와 결과물(artifacts)은 코드가 도구 결과에서 이미 판정했습니다. 그 값과 다르게 쓰지 않습니다.
- summary에는 무엇을 했고 결과가 어떤지 한두 문장으로 씁니다. 번호와 시각은 결과물에 있는 값만 씁니다.
- 실패했다면 이유를 쓰고, 다시 시켜도 해결되지 않는 문제(반려, 예약 불가, 권한 없음)면 needs_human을 true로 합니다.

## 지시서
$order

## 코드 판정
$status

## 결과물
$artifacts

## 도구 호출 기록
$log

## Agent의 마지막 말
$reply
