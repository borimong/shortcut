import { useAuthStore } from './stores/auth.js'
import router from './router.js'

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const auth = useAuthStore()
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`

  let res
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '서버에 연결할 수 없습니다.')
  }

  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  // 로그인 요청의 401은 비밀번호 오류라서 화면에 그대로 보여 주고, 그 밖의 401만 세션 만료로 처리한다.
  if (res.status === 401 && path !== '/auth/login') {
    const redirect = router.currentRoute.value.fullPath
    auth.logout()
    router.push({ name: 'login', query: redirect === '/login' ? {} : { redirect } })
    throw new ApiError(401, data?.code ?? 'UNAUTHORIZED', '로그인이 만료되었습니다. 다시 로그인해 주세요.')
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.code ?? `HTTP_${res.status}`, data?.message ?? '요청을 처리하지 못했습니다.')
  }
  return data
}
