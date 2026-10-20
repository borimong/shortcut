import { defineStore } from 'pinia'
import { ref } from 'vue'

// 내용을 읽을 시간은 주되 화면을 오래 가리지 않는 길이로 정했다.
const DURATION_MS = 4500

let seq = 0

export const useToastStore = defineStore('toast', () => {
  const items = ref([])

  function push(kind, message, code) {
    const id = ++seq
    items.value.push({ id, kind, message, code })
    setTimeout(() => dismiss(id), DURATION_MS)
  }

  function dismiss(id) {
    items.value = items.value.filter((t) => t.id !== id)
  }

  const info = (message) => push('info', message)
  const error = (err) => push('error', err?.message ?? String(err), err?.code)

  return { items, info, error, dismiss }
})
