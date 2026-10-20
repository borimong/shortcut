const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

export function dateWithWeekday(ymd) {
  if (!ymd) return ''
  const [y, m, d] = ymd.split('-').map(Number)
  const day = new Date(y, m - 1, d).getDay()
  return `${y}.${String(m).padStart(2, '0')}.${String(d).padStart(2, '0')} (${WEEKDAYS[day]})`
}

export function dateTime(iso) {
  if (!iso) return ''
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(t.getMonth() + 1)}.${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}`
}

export function won(n) {
  if (n === null || n === undefined) return ''
  return `${Number(n).toLocaleString('ko-KR')}원`
}

export function signedWon(n) {
  if (n === null || n === undefined) return ''
  return `${n > 0 ? '+' : ''}${won(n)}`
}

// 제안 API는 "v2" 문자열을, 콜시트 API는 숫자를 줄 수 있어서 표기를 하나로 맞춘다.
export function ver(v) {
  if (v === null || v === undefined || v === '') return ''
  return String(v).startsWith('v') ? String(v) : `v${v}`
}

export function addMinutes(hhmm, minutes) {
  const [h, m] = hhmm.split(':').map(Number)
  const total = h * 60 + m + minutes
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}
