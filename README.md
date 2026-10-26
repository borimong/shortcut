# ShortCut: 촬영 콜시트 재계획 AI Agent

촬영 당일 변수(우천, 배우 일정, 장소 취소, 장비 고장, 재난 문자)가 생기면 계약과 법규를 지키는 재계획안을 근거와 함께 만들고, 필수 승인자 전원의 승인을 거쳐 확정한 뒤 예약, 렌탈, 허가, 차량, 연락, 장부 처리까지 실행하는 서비스입니다.

| 폴더 | 내용 |
|---|---|
| [`shortcut-app/`](shortcut-app/README.md) | 서비스 전체 코드(화면, API, Agent, MCP 서버 3종, 평가). 실행 방법, 평가 결과, 데이터 출처, 역할과 기여는 이 폴더의 README에 있습니다 |
| [`callsheet-agent/`](callsheet-agent/contracts/README.md) | Phase 1 설계 때 만든 계약 문서와 예시 데이터(기록용, 현재 코드와 다를 수 있음) |

- Phase 1(AI Agent Capstone) 제출 시점은 `phase1-end` 태그입니다. Phase 2(AI 서비스 개발 Mini-project)는 이 태그 이후의 변경입니다.
- 비밀값은 저장소에 없습니다. `shortcut-app/.env.example`을 `.env`로 복사해 채웁니다.
