<script setup>
import { computed } from 'vue'
import { dateTime } from '../format.js'

// backend ForecastView: source(SEED, LIVE, SEED_FALLBACK), updatedAt, stale, manual
const props = defineProps({ forecast: { type: Object, default: null } })

const line = computed(() => {
  const f = props.forecast
  if (!f) return null
  const manual = f.manual ? ', 현장 입력 반영' : ''
  if (f.source === 'LIVE' && f.stale) {
    return { text: `실시간 예보 갱신 실패, ${dateTime(f.updatedAt)}에 받은 예보 사용${manual}`, warn: true }
  }
  if (f.source === 'LIVE') return { text: `실시간 예보(Open-Meteo), ${dateTime(f.updatedAt)} 갱신${manual}`, warn: false }
  if (f.source === 'SEED_FALLBACK') return { text: `실시간 예보를 아직 받지 못해 시드 예보 사용${manual}`, warn: true }
  return { text: `시연용 고정 예보${manual}`, warn: false }
})
</script>

<template>
  <p v-if="line" :class="['text-xs', line.warn ? 'text-destructive' : 'text-muted-foreground']">{{ line.text }}</p>
</template>
