export const CHANGE_ROLES = ['PRODUCTION_MANAGER', 'AD1', 'DIRECTOR']

// 시드 계정이 모두 같은 촬영일 하나를 쓰므로 목록 조회 기준을 한 곳에 둔다.
export const SHOOT_DAY_ID = 1

export const DEMO_ACCOUNTS = [
  { username: 'pd', name: '한서윤', role: 'PRODUCER', title: '제작 PD (예산 권한자)' },
  { username: 'manager', name: '오지훈', role: 'PRODUCTION_MANAGER', title: '제작실장' },
  { username: 'director', name: '강민재', role: 'DIRECTOR', title: '연출감독' },
  { username: 'ad1', name: '윤하린', role: 'AD1', title: '1조감독' },
  { username: 'ad2', name: '서도현', role: 'AD2', title: '2조감독' },
  { username: 'dop', name: '문태오', role: 'DOP', title: '촬영감독 (장비)' },
  { username: 'sound', name: '배수아', role: 'SOUND', title: '동시녹음팀장 (소음)' },
  { username: 'crew', name: '임채원', role: 'CREW', title: '연출부원 (열람만)' }
]

export const ROLE_TITLES = Object.fromEntries(DEMO_ACCOUNTS.map((a) => [a.role, a.title]))

export const EVENT_TYPES = [
  { value: 'RAIN', label: '우천', hint: '예: 13시 이후 한강 공원 강수확률이 80%로 올라갔습니다.' },
  { value: 'ACTOR_SCHEDULE', label: '배우 일정', hint: '예: 배우 A가 15시까지만 촬영 가능하다고 연락이 왔습니다.' },
  { value: 'LOCATION_CANCEL', label: '장소 취소', hint: '예: 성수 스튜디오 오후 대관이 취소되었습니다.' },
  { value: 'EQUIPMENT_FAILURE', label: '장비 고장', hint: '예: 드론 배터리 불량으로 오늘 비행이 어렵습니다.' },
  { value: 'DISASTER', label: '천재지변', hint: '예: 서울 영등포구에 호우 경보 재난 문자가 발송되었습니다.' }
]

export const NODE_ORDER = [
  'detect_change',
  'analyze_impact',
  'collect_constraints',
  'reevaluate_plans',
  'compose_plan',
  'validation_gate',
  'self_review',
  'request_approval',
  'commit_plan',
  'publish'
]

export const NODE_LABELS = {
  detect_change: '변경 감지',
  analyze_impact: '영향 분석',
  collect_constraints: '제약 수집',
  reevaluate_plans: '1/2/3안 재평가',
  compose_plan: '최적안 구성',
  validation_gate: '검증 게이트',
  self_review: '자체 검토',
  request_approval: '다중 승인 대기',
  commit_plan: '예약과 확정',
  publish: '공지와 알림',
  report_human: '사람에게 보고',
  suggest_alternatives: '4안 구성'
}

export const STATUS = {
  PENDING: ['대기', 'wait'],
  APPROVED: ['승인', 'ok'],
  REJECTED: ['거절', 'bad'],
  CANCELLED: ['취소됨', 'wait'],
  STALE: ['오래됨', 'stale'],
  COMMITTED: ['확정', 'ok'],
  QUEUED: ['대기열', 'wait'],
  RUNNING: ['진행 중', 'run'],
  WAITING_APPROVAL: ['승인 대기', 'run'],
  DONE: ['완료', 'ok'],
  FAILED: ['실패', 'bad'],
  NEEDS_HUMAN: ['사람 확인 필요', 'stale'],
  PASS: ['통과', 'ok'],
  WARN: ['경고', 'stale']
}

export const CONSTRAINT_LABELS = {
  SCHEDULE: '일정',
  CONTRACT: '배우 계약',
  LAW: '법규 (주 52시간, 촬영 허가)',
  BUDGET: '예산 상한',
  NO_FLY_ZONE: '비행금지 구역',
  DISASTER: '재난 문자',
  WEATHER: '날씨',
  EXTRA: '추가 제약'
}

export const SCORE_LABELS = {
  location: '장소 적합도',
  equipment: '장비 적합도',
  weather: '날씨',
  budget: '예산 여유',
  time: '종료 시각',
  distance: '이동 거리'
}

export const METRIC_LABELS = [
  ['loops', '루프'],
  ['toolCalls', '도구 호출'],
  ['llmCalls', 'LLM 호출'],
  ['tokens', '토큰'],
  ['costUsd', '비용 (USD)'],
  ['latencyMs', '소요 시간'],
  ['retries', '재시도'],
  ['fallbacks', '대체 경로']
]

// 거절할 때 고르는 문제 요소다. Agent는 고른 요소만 바꾸고 나머지는 거절된 안을 유지한다.
export const ISSUE_OPTIONS = [
  { value: 'LOCATION', label: '장소' },
  { value: 'TIME', label: '시간대' },
  { value: 'EQUIPMENT', label: '장비' },
  { value: 'COST', label: '비용' },
  { value: 'OTHER', label: '기타' }
]

export const ISSUE_LABELS = Object.fromEntries(ISSUE_OPTIONS.map((o) => [o.value, o.label]))

export const REVIEW_LABELS = {
  evidence: '하드 제약 근거',
  rejection: '거절 사유 보완',
  optimization: '최적화 균형',
  explanation: '설명 구체성',
  risk: '실행 위험'
}

export const REVIEW_ACTIONS = {
  REWRITE: '설명과 근거 보완',
  NEXT_CANDIDATE: '다른 조합으로 교체',
  MORE_EVIDENCE: '규정 근거 추가 검색'
}
