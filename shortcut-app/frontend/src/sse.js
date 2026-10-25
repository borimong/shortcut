import { useAuthStore } from './stores/auth.js'

export const TERMINAL_EVENTS = ['DONE', 'FAILED', 'NEEDS_HUMAN', 'SUPERSEDED']

// EventSource는 Authorization 헤더를 붙일 수 없어서 서버와 약속한 access_token 쿼리로 토큰을 보낸다.
// after를 주면 그 이벤트 id 다음부터 받는다. 작업이 끝나 닫힌 스트림을 수정 요청 뒤에 이어 열 때 쓴다.
export function openStream(path, handlers, { onStateChange, after } = {}) {
  const auth = useAuthStore()
  const params = [`access_token=${encodeURIComponent(auth.token ?? '')}`]
  if (after !== undefined && after !== null && after >= 0) params.push(`after=${after}`)
  const sep = path.includes('?') ? '&' : '?'
  const source = new EventSource(`/api${path}${sep}${params.join('&')}`)
  let lastId = after ?? -1

  for (const [type, handler] of Object.entries(handlers)) {
    source.addEventListener(type, (event) => {
      const id = Number(event.lastEventId)
      // 저장 이벤트 재전송과 실시간 전달이 겹치는 순간에 같은 이벤트가 두 번 올 수 있어 id로 거른다.
      if (event.lastEventId !== '' && Number.isFinite(id)) {
        if (id <= lastId) return
        lastId = id
      }
      let data = null
      try {
        data = JSON.parse(event.data)
      } catch {
        data = event.data
      }
      // 핸들러는 두 번째 인자로 이벤트 id를 받는다. 생각 기록의 수정 요청이 이 id로 대상을 고른다.
      handler(data, Number.isFinite(id) && event.lastEventId !== '' ? id : null)
      if (TERMINAL_EVENTS.includes(type)) source.close()
    })
  }

  if (onStateChange) {
    source.onopen = () => onStateChange('open')
    // 재연결은 EventSource가 스스로 하므로 여기서는 상태만 알린다.
    source.onerror = () => onStateChange(source.readyState === EventSource.CLOSED ? 'closed' : 'reconnecting')
  }
  return source
}
