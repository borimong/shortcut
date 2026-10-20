<script setup>
import { computed } from 'vue'
import { MapPin } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { originalPlan, newPlan } from '@/data/demo.js'

const props = defineProps({ version: { type: String, default: 'after' } })

const rows = computed(() => (props.version === 'after' ? newPlan : originalPlan.map(s => ({ ...s, changes: [] }))))

// 스트립 색: 실내/야외 × 낮/밤 (촬영 현장 스트립보드 관례)
function tone(outdoor, dayNight) {
  if (outdoor) return dayNight === '낮' ? 'bg-strip-ext-day' : 'bg-strip-ext-night text-primary-foreground'
  return dayNight === '낮' ? 'bg-background border' : 'bg-strip-int-night text-primary-foreground'
}

const minutes = (t) => {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}
const total = computed(() => {
  const mins = rows.value.reduce((sum, s) => sum + (minutes(s.end) - minutes(s.start)), 0)
  return `${Math.floor(mins / 60)}시간${mins % 60 ? ` ${mins % 60}분` : ''}`
})
</script>

<template>
  <div class="flex flex-col gap-[3px] text-[13px]" role="table" aria-label="스트립보드">
    <div v-for="s in rows" :key="s.id" role="row"
         :class="cn('grid min-w-0 grid-cols-[38px_40px_minmax(0,1fr)_28px_48px_minmax(0,0.8fr)_44px] items-center gap-2 rounded-xs px-3 py-2 max-[560px]:grid-cols-[34px_minmax(0,1fr)_44px_44px]', tone(s.outdoor, s.dayNight), s.changes.length && 'ring-2 ring-brand ring-inset')">
      <span class="mono">{{ s.id }}</span>
      <span class="max-[560px]:hidden">{{ s.outdoor ? '야외' : '실내' }}</span>
      <span class="truncate font-semibold">{{ s.title }}</span>
      <span class="max-[560px]:hidden">{{ s.dayNight }}</span>
      <span class="mono">{{ s.start }}</span>
      <span class="flex items-center gap-1 truncate max-[560px]:hidden"><MapPin class="size-3" />{{ s.location }}</span>
      <Badge v-if="s.changes.length" variant="brand" class="justify-self-end text-[11px]">변경</Badge>
    </div>
    <div class="mt-0.5 rounded-xs bg-strip-break py-1.5 text-center text-xs text-primary-foreground">1일차 종료, 총 촬영 {{ total }}</div>
  </div>
</template>
