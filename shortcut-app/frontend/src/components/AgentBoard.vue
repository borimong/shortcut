<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowDown } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { AGENTS, AGENT_STAGES, AGENT_STATUS } from '../labels.js'

// agents는 TaskView가 이벤트로 채우는 Agent별 상태다. { 이름: { status, action, startedAt, elapsedMs, thought } }
const props = defineProps({
  agents: { type: Object, required: true },
  // 계획 단계가 끝나기 전에는 실행팀 카드를 흐리게 보여 준다.
  executionStarted: { type: Boolean, default: false }
})

// 진행 중인 카드의 경과 시간을 1초마다 다시 그린다.
const now = ref(Date.now())
let ticker = null
onMounted(() => (ticker = setInterval(() => (now.value = Date.now()), 1000)))
onBeforeUnmount(() => clearInterval(ticker))

function info(name) {
  const s = props.agents[name] ?? {}
  const [label, variant] = AGENT_STATUS[s.status] ?? AGENT_STATUS.idle
  let ms = s.elapsedMs ?? 0
  if (s.status === 'running' && s.startedAt) ms = now.value - s.startedAt
  return { ...AGENTS[name], name, ...s, statusLabel: label, variant, elapsed: ms >= 1000 ? `${Math.round(ms / 1000)}초` : '' }
}

const top = computed(() => ['planner', 'supervisor'].map(info))
const stages = computed(() => AGENT_STAGES.map((st) => ({ ...st, cards: st.agents.map(info) })))
const runningCount = computed(() => Object.values(props.agents).filter((s) => s.status === 'running').length)

const DOT = {
  running: 'bg-primary',
  done: 'bg-success',
  failed: 'bg-destructive',
  waiting: 'bg-warning',
  needs_human: 'bg-warning',
  skipped: 'bg-muted-foreground/30',
  idle: 'bg-muted-foreground/40'
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <span>지금 일하는 Agent</span>
      <Badge :variant="runningCount ? 'info' : 'secondary'">{{ runningCount }}명</Badge>
    </div>

    <div class="grid gap-3 sm:grid-cols-2">
      <article
        v-for="c in top"
        :key="c.name"
        class="flex min-w-0 flex-col gap-1.5 rounded-lg border border-border p-3"
        :class="{ 'ring-2 ring-primary/40': c.status === 'running', 'opacity-60': c.name === 'supervisor' && !executionStarted }"
      >
        <header class="flex items-center gap-2">
          <span class="relative flex size-2.5 shrink-0">
            <span v-if="c.status === 'running'" class="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60"></span>
            <span class="relative inline-flex size-2.5 rounded-full" :class="DOT[c.status] ?? DOT.idle"></span>
          </span>
          <span class="font-medium">{{ c.label }}</span>
          <Badge :variant="c.variant" class="ml-auto">{{ c.statusLabel }}</Badge>
        </header>
        <p class="text-xs text-muted-foreground">{{ c.role }}</p>
        <p v-if="c.action" class="truncate text-sm" :title="c.action">
          {{ c.action }}<span v-if="c.elapsed" class="mono ml-1.5 text-xs text-muted-foreground">{{ c.elapsed }}</span>
        </p>
        <p v-if="c.thought" class="line-clamp-2 text-xs text-muted-foreground" :title="c.thought">판단: {{ c.thought }}</p>
      </article>
    </div>

    <div class="flex justify-center text-muted-foreground" aria-hidden="true"><ArrowDown class="size-4" /></div>

    <!-- 단계 열을 나란히 두어 같은 단계의 Agent가 동시에 움직이는 것을 한눈에 보이게 한다 -->
    <div class="grid gap-3 md:grid-cols-3" :class="{ 'opacity-60': !executionStarted }">
      <section v-for="st in stages" :key="st.stage" class="flex min-w-0 flex-col gap-2 rounded-lg bg-muted/40 p-2.5">
        <h4 class="flex flex-wrap items-baseline gap-x-2 text-sm font-medium">
          {{ st.title }}<span class="text-xs font-normal text-muted-foreground">{{ st.hint }}</span>
        </h4>
        <article
          v-for="c in st.cards"
          :key="c.name"
          class="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-background p-2.5"
          :class="{ 'ring-2 ring-primary/40': c.status === 'running', 'opacity-50': c.status === 'skipped' }"
        >
          <header class="flex items-center gap-2">
            <span class="relative flex size-2 shrink-0">
              <span v-if="c.status === 'running'" class="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60"></span>
              <span class="relative inline-flex size-2 rounded-full" :class="DOT[c.status] ?? DOT.idle"></span>
            </span>
            <span class="min-w-0 truncate text-sm font-medium">{{ c.label }}</span>
            <Badge :variant="c.variant" class="ml-auto">{{ c.statusLabel }}</Badge>
          </header>
          <p v-if="c.action" class="truncate text-xs" :title="c.action">
            {{ c.action }}<span v-if="c.elapsed" class="mono ml-1 text-muted-foreground">{{ c.elapsed }}</span>
          </p>
          <p v-else class="text-xs text-muted-foreground">{{ c.role }}</p>
          <p v-if="c.thought" class="line-clamp-2 text-xs text-muted-foreground" :title="c.thought">판단: {{ c.thought }}</p>
        </article>
      </section>
    </div>
  </div>
</template>
