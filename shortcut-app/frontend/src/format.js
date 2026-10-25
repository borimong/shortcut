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

// 앞말 받침에 맞는 조사를 붙인다. 백엔드 Josa와 같은 규칙이다. 한글은 받침, 숫자와 영문은 읽는 소리(v1 일, v2 이, L 엘)로 가른다.
// pair는 받침 있을 때 쓰는 쪽으로 준다: '은', '이', '을', '과', '으로'.
const JOSA = { 은: '는', 이: '가', 을: '를', 과: '와', 으로: '로' }

function ending(word) {
  const text = String(word).trim().replace(/\([^()]*\)$/, '').trim()
  const last = text.at(-1) ?? ''
  const code = last.charCodeAt(0)
  if (code >= 0xac00 && code <= 0xd7a3) {
    const jong = (code - 0xac00) % 28
    return jong === 0 ? 'none' : jong === 8 ? 'rieul' : 'other'
  }
  if (/[0-9]/.test(last)) {
    const digits = text.match(/[0-9,]+$/)[0].replaceAll(',', '')
    if (/^0+$/.test(digits)) return 'other'
    if (digits.endsWith('0')) return 'other'
    return '178'.includes(last) ? 'rieul' : '36'.includes(last) ? 'other' : 'none'
  }
  if (/[a-z]/i.test(last)) {
    if (/(km|mm|cm|kg|mg|ml)$/i.test(text)) return 'none'
    return 'LR'.includes(last.toUpperCase()) ? 'rieul' : 'MN'.includes(last.toUpperCase()) ? 'other' : 'none'
  }
  return 'none'
}

export function josa(word, pair) {
  const e = ending(word)
  const batchim = pair === '으로' ? e === 'other' : e !== 'none'
  return `${word}${batchim ? pair : JOSA[pair]}`
}

export function addMinutes(hhmm, minutes) {
  const [h, m] = hhmm.split(':').map(Number)
  const total = h * 60 + m + minutes
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}
