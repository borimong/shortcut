import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api.js'
import { SHOOT_DAY_ID } from '../labels.js'

// 자원 현황 패널과 헤더 배지가 같은 데이터를 보도록 한곳에서 불러온다.
export const useResourceStore = defineStore('resources', () => {
  const board = ref(null)
  const error = ref(null)
  const loading = ref(false)

  const all = computed(() =>
    board.value ? [...board.value.equipment, ...board.value.locations, ...board.value.actors] : []
  )
  const unavailableCount = computed(() => all.value.filter((i) => i.status !== 'OK' && i.status !== 'LIMITED').length)
  const limitedCount = computed(() => all.value.filter((i) => i.status === 'LIMITED').length)

  async function load() {
    loading.value = true
    try {
      board.value = await api(`/resources?shootDayId=${SHOOT_DAY_ID}`)
      error.value = null
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  async function save({ changes, clears, replan }) {
    const result = await api('/resources/changes', {
      method: 'POST',
      body: { shootDayId: SHOOT_DAY_ID, dataVersion: board.value.dataVersion, replan, changes, clears }
    })
    await load()
    return result
  }

  return { board, error, loading, all, unavailableCount, limitedCount, load, save }
})
