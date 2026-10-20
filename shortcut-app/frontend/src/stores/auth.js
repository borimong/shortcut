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

  async function login(username, password) {
    const res = await api('/auth/login', { method: 'POST', body: { username, password } })
    token.value = res.accessToken
    user.value = res.user
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: token.value, user: user.value }))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  return { token, user, isLoggedIn, canSubmitChange, login, logout }
})
