import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api.js'
import { CHANGE_ROLES } from '../labels.js'

const STORAGE_KEY = 'shortcut.auth'

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? {}
  } catch {
    return {}
  }
}

export const useAuthStore = defineStore('auth', () => {
  const saved = load()
  const token = ref(saved.token ?? null)
  const user = ref(saved.user ?? null)

  const isLoggedIn = computed(() => Boolean(token.value))
  const canSubmitChange = computed(() => CHANGE_ROLES.includes(user.value?.role))
  const isAdmin = computed(() => Boolean(user.value?.admin))

  async function login(username, password) {
    const res = await api('/auth/login', { method: 'POST', body: { username, password } })
    token.value = res.accessToken
    user.value = res.user
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: token.value, user: user.value }))
  }

  // 관리자 지정이나 탈퇴는 로그인 뒤에도 바뀔 수 있어서 화면을 열 때 내 정보를 다시 읽는다.
  async function refresh() {
    if (!token.value) return
    try {
      user.value = await api('/me')
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: token.value, user: user.value }))
    } catch {
      // 401이면 api()가 이미 로그아웃시킨다. 그 밖의 오류는 저장된 정보를 그대로 쓴다.
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  return { token, user, isLoggedIn, canSubmitChange, isAdmin, login, logout, refresh }
})
