import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api.js'
import { openStream } from '../sse.js'
import { useToastStore } from './toast.js'

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref([])
  const unreadCount = ref(0)
  // 화면마다 따로 구독하지 않고 헤더의 한 연결을 나눠 쓰도록 마지막 수신 내용을 노출한다.
  const lastNotification = ref(null)
  const lastApprovalUpdate = ref(null)
  let source = null

  async function refresh() {
    const res = await api('/notifications')
    items.value = res.items ?? []
    unreadCount.value = res.unreadCount ?? 0
  }

  function connect() {
    if (source) return
    source = openStream('/notifications/stream', {
      NOTIFICATION(n) {
        if (items.value.some((i) => i.id === n.id)) return
        items.value.unshift(n)
        if (!n.read) unreadCount.value += 1
        lastNotification.value = { ...n, receivedAt: Date.now() }
        useToastStore().info(n.title)
      },
      APPROVAL_UPDATED(u) {
        lastApprovalUpdate.value = { ...u, receivedAt: Date.now() }
      }
    })
  }

  function disconnect() {
    source?.close()
    source = null
    items.value = []
    unreadCount.value = 0
  }

  async function markRead(n) {
    if (n.read) return
    await api(`/notifications/${n.id}/read`, { method: 'POST' })
    n.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }

  async function markAllRead() {
    await api('/notifications/read-all', { method: 'POST' })
    items.value.forEach((i) => (i.read = true))
    unreadCount.value = 0
  }

  return {
    items,
    unreadCount,
    lastNotification,
    lastApprovalUpdate,
    refresh,
    connect,
    disconnect,
    markRead,
    markAllRead
  }
})
