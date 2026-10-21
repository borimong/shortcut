// 콜시트를 바꿀 수 있는 사람은 제작 PD와 연출 PD다. 제작 조직은 제작자, 제작 PD, 제작실장, 제작부장, 제작부원 순이다.
export const CHANGE_ROLES = ['PRODUCER', 'DIRECTOR']

export const DEMO_ACCOUNTS = [
  { username: 'pd', name: '한서윤', role: 'PRODUCER', title: '제작 PD (예산 권한자)' },
  { username: 'manager', name: '오지훈', role: 'PRODUCTION_MANAGER', title: '제작실장' },
  { username: 'director', name: '강민재', role: 'DIRECTOR', title: '연출 PD (연출감독)' },
  { username: 'ad1', name: '윤하린', role: 'AD1', title: '1조감독' },
  { username: 'ad2', name: '서도현', role: 'AD2', title: '2조감독' },
  { username: 'dop', name: '문태오', role: 'DOP', title: '촬영감독 (장비)' },
  { username: 'sound', name: '배수아', role: 'SOUND', title: '동시녹음팀장 (소음)' },
  { username: 'crew', name: '임채원', role: 'CREW', title: '연출부원 (열람 전용)' }
]

export const ROLE_TITLES = Object.fromEntries(DEMO_ACCOUNTS.map((a) => [a.role, a.title]))

// 승인은 제작부, 연출부, 기술부서 세 곳에서 받는다. 승인 현황 표를 이 순서로 묶는다.
export const DEPARTMENTS = [
  { name: '제작부', roles: ['PRODUCER', 'PRODUCTION_MANAGER'] },
  { name: '연출부', roles: ['DIRECTOR', 'AD1', 'AD2'] },
  { name: '기술부서', roles: ['DOP', 'SOUND'] }
]

// 유형마다 무엇을 적으면 Agent가 바로 판단할 수 있는지 보여 주는 예시다. 언제, 어디서, 무엇이, 얼마나, 누가 연락했는지를 담는다.
export const EVENT_TYPES = [
  {
    value: 'RAIN',
    label: '우천',
    hint: '예) 기상청 단기예보 기준 13시부터 한강 공원에 시간당 8mm 비가 예보되었습니다. 오후 산책 씬(S12, S13)은 야외 촬영이 어렵고, 비는 17시쯤 그칠 것으로 보입니다.'
  },
  {
    value: 'ACTOR_SCHEDULE',
    label: '배우 일정',
    hint: '예) 배우 A 매니저에게서 10시 40분에 연락이 왔습니다. 오전 광고 촬영이 길어져 오늘은 15시까지만 촬영할 수 있고, 현장 도착은 13시 30분 예정입니다.'
  },
  {
    value: 'LOCATION_CANCEL',
    label: '장소 취소',
    hint: '예) 성수 스튜디오 담당자가 오늘 14~18시 대관을 취소했습니다(누수 공사). 가예약 R-2031도 함께 취소되었고, 대체 공간은 제공되지 않습니다.'
  },
  {
    value: 'EQUIPMENT_FAILURE',
    label: '장비 고장',
    hint: '예) 촬영팀이 오전 점검 중 반사판 2개가 모두 파손된 것을 확인했습니다. 오늘 오후 촬영에는 쓸 수 없고, 렌탈사 대체품은 16시 이후에나 도착합니다.'
  },
  {
    value: 'DISASTER',
    label: '천재지변',
    hint: '예) 12시 10분에 서울 영등포구에 호우 경보 긴급재난문자가 발송되었습니다. 13~17시 야외 활동 자제 권고이며, 한강 공원 출입이 통제될 수 있습니다.'
  },
  {
    value: 'OTHER',
    label: '기타',
    hint: '예) 오후 촬영지 주변 도로가 마라톤 행사로 12~15시 통제됩니다. 장비 차량 진입이 어려워 촬영 시작이 1시간가량 늦어질 수 있습니다.'
  }
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
  SUPERSEDED: ['대체됨', 'stale'],
  PASS: ['통과', 'ok'],
  WARN: ['경고', 'stale']
}

// 자원 현황 패널의 상태 이름과 배지 모양이다. 장비는 OK, BROKEN, REPAIR, 장소는 OK, CANCELLED, 배우는 OK, ABSENT, LIMITED를 쓴다.
export const RESOURCE_STATUS = {
  OK: ['정상', 'success'],
  BROKEN: ['고장', 'destructive'],
  REPAIR: ['수리 중', 'warning'],
  CANCELLED: ['취소', 'destructive'],
  ABSENT: ['불참', 'destructive'],
  LIMITED: ['시간 제한', 'warning']
}

// 자원 종류마다 고를 수 있는 상태다.
export const RESOURCE_OPTIONS = {
  equipment: ['OK', 'BROKEN', 'REPAIR'],
  locations: ['OK', 'CANCELLED'],
  actors: ['OK', 'ABSENT', 'LIMITED']
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
