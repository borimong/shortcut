// 데모 시나리오: 가상 드라마 7화, 촬영 전날 밤 호우주의보로 재계획
// 나중에 API가 생기면 같은 형식으로 응답을 받는다

export const project = {
  title: '드라마 〈밤의 정류장〉',
  episode: '7화',
  shootDate: '11월 12일 (목)',
  callTime: '06:30',
}

export const weatherAlert = {
  kind: '호우주의보',
  area: '서울 서남권',
  effective: '내일 14:00 발효',
  location: '한강공원 (S12, S13)',
}

export const originalPlan = [
  { id: 'S10', title: '정류장 대기실, 첫 만남', outdoor: false, dayNight: '낮', location: '성수 스튜디오', start: '08:00', end: '09:30', cast: ['배우 A', '배우 B'] },
  { id: 'S11', title: '편의점 계산대', outdoor: false, dayNight: '낮', location: '성수 스튜디오', start: '09:30', end: '11:00', cast: ['배우 A', '배우 C'] },
  { id: 'S12', title: '강변 자전거 추격', outdoor: true, dayNight: '낮', location: '한강공원', start: '13:00', end: '15:00', cast: ['배우 A', '배우 B'] },
  { id: 'S13', title: '노을 아래 고백', outdoor: true, dayNight: '낮', location: '한강공원', start: '15:00', end: '16:30', cast: ['배우 B', '배우 D'] },
  { id: 'S14', title: '막차 버스 안', outdoor: false, dayNight: '밤', location: '파주 세트장', start: '17:30', end: '19:00', cast: ['배우 C', '배우 E'] },
]

export const newPlan = [
  { ...originalPlan[0], changes: [] },
  { ...originalPlan[1], changes: [] },
  {
    ...originalPlan[2], outdoor: false, location: '성수 스튜디오', start: '11:00', end: '13:00',
    changes: ['장소 변경', '시간대 변경'],
    from: { location: '한강공원', start: '13:00', end: '15:00' },
  },
  {
    ...originalPlan[3], outdoor: false, location: '파주 세트장', start: '14:30', end: '16:00',
    changes: ['장소 변경', '시간대 변경', '추가 비용'],
    from: { location: '한강공원', start: '15:00', end: '16:30' },
  },
  {
    ...originalPlan[4], start: '16:30', end: '18:00',
    changes: ['시간대 변경'],
    from: { location: '파주 세트장', start: '17:30', end: '19:00' },
  },
]

export const evidence = [
  { code: 'H6', text: '한강공원 호우주의보, 내일 14:00 발효' },
  { code: 'H1', text: '배우 A 계약 제7조, 하루 최대 12시간' },
  { code: 'H2', text: '성수 스튜디오 이용 10:00~18:00' },
  { code: 'H4', text: '추가 비용 32만 원, 회차 잔액 이내' },
]

export const unresolved = ['배우 D 매니저 회신 대기 (14:30 이전 집합 가능 여부)']

export const planSummary = {
  version: 'v8',
  round: 2,
  maxRound: 3,
  movedScenes: 3,
  extraCost: '32만 원',
  travelSaved: '4km',
}

export const approvals = [
  { role: '연출감독', department: '연출부', scope: '장면 의도와 장소', status: 'APPROVED', at: '22:12' },
  { role: '1조감독', department: '연출부', scope: '촬영 순서와 시간', status: 'APPROVED', at: '22:14' },
  { role: '2조감독', department: '연출부', scope: '이동 동선', status: 'PENDING' },
  { role: '동시녹음팀장', department: '기술부서', scope: '장소 소음', status: 'REJECTED', at: '22:17', reason: '성수 스튜디오 오후 공사 소음, 동시녹음 불가' },
  { role: '촬영감독', department: '기술부서', scope: '장소와 조명 조건', status: 'APPROVED', at: '22:15' },
  { role: '제작 PD', department: '제작부', scope: '추가 비용 32만 원', status: 'PENDING' },
]

export const notices = [
  { kind: '거절', at: '방금', text: '동시녹음팀장이 변경안 v8을 거절했습니다' },
  { kind: '승인 요청', at: '11분 전', text: '변경안 v8 승인이 필요합니다 (2조감독)' },
  { kind: '변경 공지', at: '13분 전', text: '내일 14시 한강공원 호우주의보로 계획을 다시 짭니다' },
]

export const recipients = [
  { name: '김서윤', role: '배우 A', channel: '문자', delivery: 'SENT', viewedAt: '06:02', confirmedAt: '06:03' },
  { name: '박도현', role: '배우 B', channel: '문자', delivery: 'SENT', viewedAt: '06:10' },
  { name: '이하린', role: '1조감독', channel: '메일', delivery: 'SENT', viewedAt: '05:58', confirmedAt: '05:58' },
  { name: '정우진', role: '동시녹음팀장', channel: '문자', delivery: 'SENT', viewedAt: '06:05', confirmedAt: '06:07' },
  { name: '최민서', role: '분장팀', channel: '메일', delivery: 'BOUNCED' },
  { name: '한지호', role: '그립팀', channel: '문자', delivery: 'SENT' },
]

export const deliveryStats = { sent: 24, bounced: 1, viewed: 21, confirmed: 18 }

export const nightLog = [
  { at: '22:00', who: '기상청', text: '내일 14시 호우주의보' },
  { at: '22:10', who: '조감독', text: '감독님, S12 한강 내일 비 온대요' },
  { at: '22:40', who: '조감독', text: '매니저님, A 배우 내일 11시 가능할까요?' },
  { at: '23:30', who: '조감독', text: '음향팀장님, 성수 오후 괜찮으세요?' },
  { at: '01:00', who: '조감독', text: '수정 콜시트 다시 보냅니다…' },
]
