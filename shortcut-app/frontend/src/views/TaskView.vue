<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Check, ExternalLink, X } from '@lucide/vue'
import StatusBadge from '../components/StatusBadge.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '../api.js'
import { TERMINAL_EVENTS, openStream } from '../sse.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime, won, ver } from '../format.js'
import { METRIC_LABELS, NODE_LABELS, NODE_ORDER, ROLE_TITLES } from '../labels.js'

const route = useRoute()
const toast = useToastStore()

const KIND_LABELS = { REPLAN: '재계획', ASK: '근거 질문' }

const task = ref(null)
const status = ref('')
const loop = ref(0)
const nodes = reactive({})
const extraNodes = ref([])
const tools = ref([])
// 전체 기록 탭에 쓰는 시간순 이벤트 목록. 도구 항목은 tools와 같은 객체라 끝나면 함께 갱신된다.
const log = ref([])
const tokenText = ref('')
const approval = ref(null)
const result = ref(null)
const connection = ref('')
// 저장된 이벤트를 다시 받는 동안 카드가 하나씩 끼어들며 화면이 밀리지 않게, 이벤트가 잠시 멈출 때까지 뼈대만 보여 준다.
const settled = ref(false)
let settleTimer = null
let fallbackTimer = null
let source = null

function settle() {
  clearTimeout(settleTimer)
  clearTimeout(fallbackTimer)
  settled.value = true
}

function settleSoon() {
  if (settled.value) return
  clearTimeout(settleTimer)
  settleTimer = setTimeout(settle, 250)
}

function reset() {
  source?.close()
  source = null
  task.value = null
  status.value = ''
  loop.value = 0
  for (const key of Object.keys(nodes)) delete nodes[key]
  NODE_ORDER.forEach((id) => (nodes[id] = { status: 'pending', loop: 0, detail: '' }))
  extraNodes.value = []
  tools.value = []
  log.value = []
  tokenText.value = ''
  approval.value = null
  result.value = null
  connection.value = ''
  settled.value = false
  clearTimeout(settleTimer)
  clearTimeout(fallbackTimer)
}

const handlers = {
  NODE(p) {
    if (!nodes[p.node]) {
      nodes[p.node] = { status: 'pending', loop: 0, detail: '' }
      extraNodes.value.push(p.node)
    }
    const n = nodes[p.node]
    n.status = p.phase === 'end' ? 'done' : 'running'
    n.loop = p.loop ?? n.loop
    n.label = p.label
    if (p.detail) n.detail = typeof p.detail === 'string' ? p.detail : JSON.stringify(p.detail)
    log.value.push({ kind: 'node', end: p.phase === 'end', label: NODE_LABELS[p.node] ?? p.label ?? p.node, loop: p.loop, detail: p.phase === 'end' ? n.detail : '' })
    if ((p.loop ?? 0) > loop.value) loop.value = p.loop
    if (!result.value) status.value = 'RUNNING'
  },
  TOOL_START(p) {
    const entry = reactive({ kind: 'tool', tool: p.tool, server: p.server, args: p.args, done: false })
    tools.value.push(entry)
    log.value.push(entry)
  },
  TOOL_END(p) {
    const open = [...tools.value].reverse().find((t) => t.tool === p.tool && !t.done)
    const entry = open ?? { tool: p.tool, server: '', args: null }
    Object.assign(entry, { done: true, ok: p.ok, ms: p.ms, preview: p.preview })
    if (!open) {
      entry.kind = 'tool'
      tools.value.push(entry)
      log.value.push(entry)
    }
  },
  TOKEN(p) {
    tokenText.value += p.text ?? ''
  },
  APPROVAL_REQUIRED(p) {
    approval.value = p
    log.value.push({ kind: 'mark', tone: 'info', text: `변경안 ${ver(p.versionNo)} 승인 요청` })
    status.value = 'WAITING_APPROVAL'
  },
  DONE(p) {
    result.value = { type: 'DONE', ...p }
    log.value.push({ kind: 'mark', tone: 'success', text: '작업 완료' })
    status.value = 'DONE'
  },
  FAILED(p) {
    result.value = { type: 'FAILED', ...p }
    log.value.push({ kind: 'mark', tone: 'destructive', text: '작업 실패' })
    status.value = 'FAILED'
    for (const n of Object.values(nodes)) if (n.status === 'running') n.status = 'failed'
  },
  NEEDS_HUMAN(p) {
    result.value = { type: 'NEEDS_HUMAN', ...p }
    log.value.push({ kind: 'mark', tone: 'warning', text: '사람 확인 필요' })
    status.value = 'NEEDS_HUMAN'
  }
}

async function start(id) {
  reset()
  try {
    task.value = await api(`/ai/tasks/${id}`)
    status.value = task.value.status
  } catch (e) {
    toast.error(e)
    settle()
    return
  }
  // 응답을 기다리는 사이 다른 작업으로 이동했다면 이전 작업의 스트림을 열지 않는다.
  if (route.params.id !== id) return
  const tracked = Object.fromEntries(
    Object.entries(handlers).map(([type, handle]) => [
      type,
      (payload) => {
        handle(payload)
        if (TERMINAL_EVENTS.includes(type)) settle()
        else settleSoon()
      }
    ])
  )
  // 이벤트가 하나도 오지 않는 작업도 있으므로 오래 기다리지 않는다.
  fallbackTimer = setTimeout(settle, 2000)
  source = openStream(`/ai/tasks/${id}/stream`, tracked, {
    onStateChange: (s) => {
      connection.value = s
      if (s === 'open') settleSoon()
      else if (s === 'closed') settle()
    }
  })
}

watch(() => route.params.id, (id) => id && start(id), { immediate: true })
onBeforeUnmount(() => {
  source?.close()
  clearTimeout(settleTimer)
  clearTimeout(fallbackTimer)
})

const timeline = computed(() =>
  [...NODE_ORDER, ...extraNodes.value].map((id) => ({
    ...nodes[id],
    id,
    label: NODE_LABELS[id] ?? (nodes[id]?.label || id)
  }))
)

const activity = computed(() => {
  const running = tools.value.findLast((t) => !t.done)
  if (running) return `${running.tool} 도구 호출 중`
  const node = timeline.value.findLast((n) => n.status === 'running')
  if (node) return `${node.label} 단계 진행 중`
  return ''
})

const isLive = computed(() => !result.value && connection.value !== 'closed')

function short(value) {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function metricValue(key, v) {
  if (v === null || v === undefined) return '0'
  if (key === 'latencyMs') return `${(v / 1000).toFixed(1)}초`
  if (key === 'costUsd') return `$${Number(v).toFixed(4)}`
  return Number(v).toLocaleString('ko-KR')
}

// NEEDS_HUMAN의 best와 suggestions는 형태가 고정돼 있지 않아 흔한 필드만 골라 읽는다.
function describeCandidate(c) {
  if (!c || typeof c !== 'object') return short(c)
  const loc = c.location?.name ?? c.name
  const items = c.equipment?.items ?? c.equipment
  const equip = Array.isArray(items) ? items.map((e) => e.name ?? e).join(', ') : ''
  const start = c.time?.start ?? c.start
  const end = c.time?.end ?? c.end
  const parts = [loc, equip && `장비 ${equip}`, start && `${start}~${end}`]
  const score = c.totalScore ?? c.score
  if (score !== undefined) parts.push(`점수 ${Number(score).toFixed(3)}`)
  return parts.filter(Boolean).join(', ') || short(c)
}

function describeSuggestion(s) {
  if (!s || typeof s !== 'object') return { title: short(s), meta: [] }
  const meta = []
  if (s.indoor !== undefined) meta.push(s.indoor ? '실내' : '야외')
  if (s.region) meta.push(s.region)
  if (s.distanceKm !== undefined) meta.push(`${s.distanceKm}km`)
  if (s.cost !== undefined) meta.push(won(s.cost))
  if (Array.isArray(s.keywords)) meta.push(s.keywords.join(', '))
  return { title: s.name ?? s.title ?? describeCandidate(s), meta, reason: s.reason, mock: s.source === 'OURPLACE_MOCK' }
}

function describeViolation(v) {
  if (!v || typeof v !== 'object') return short(v)
  return v.message ? `${v.message} (${v.code ?? v.constraint})` : short(v)
}
</script>

<template>
  <div class="page">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <h1 class="page-title">
          {{ KIND_LABELS[task?.kind] ?? 'Agent' }} 진행
          <span class="mono text-base font-normal text-muted-foreground">#{{ route.params.id }}</span>
        </h1>
        <p v-if="task?.question" class="text-muted-foreground">{{ task.question }}</p>
        <p v-else-if="task?.createdAt" class="text-muted-foreground">{{ dateTime(task.createdAt) }} 접수</p>
        <p v-else class="text-muted-foreground" aria-hidden="true">&nbsp;</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Badge v-if="loop" variant="info">루프 {{ loop }}</Badge>
        <StatusBadge v-if="status" :status="status" />
      </div>
    </div>

    <div v-if="!settled" class="flex flex-col gap-5" aria-busy="true" aria-label="진행 기록을 불러오는 중">
      <Skeleton class="h-11 w-full" />
      <Skeleton class="h-48 w-full" />
      <Skeleton class="h-96 w-full" />
    </div>

    <template v-else>
      <div class="flex flex-wrap items-center gap-2.5 rounded-lg border border-border px-3 py-2.5 text-sm">
        <!-- 스트림이 살아 있는 동안 점을 깜빡여 진행 중임을 보여 준다 -->
        <span class="relative flex size-2.5 shrink-0">
          <span v-if="isLive" class="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60"></span>
          <span class="relative inline-flex size-2.5 rounded-full" :class="isLive ? 'bg-success' : 'bg-muted-foreground/40'"></span>
        </span>
        <span v-if="activity && isLive">{{ activity }}</span>
        <span v-else-if="result" class="text-muted-foreground">작업이 끝났습니다.</span>
        <span v-else-if="status === 'WAITING_APPROVAL'" class="text-muted-foreground">승인 결과를 기다리고 있습니다.</span>
        <span v-else class="text-muted-foreground">Agent 이벤트를 기다리고 있습니다.</span>
        <Badge v-if="connection === 'reconnecting'" variant="warning">재연결 중</Badge>
        <Badge v-else-if="connection === 'closed' && !result" variant="destructive">연결 끊김</Badge>
      </div>

      <Card v-if="approval" class="ring-primary/60">
        <CardHeader>
          <CardTitle>변경안 {{ ver(approval.versionNo) }} 승인 대기</CardTitle>
          <CardDescription v-if="approval.summary" class="text-foreground">{{ approval.summary }}</CardDescription>
        </CardHeader>
        <CardContent v-if="approval.requiredApprovers?.length" class="flex flex-wrap items-center gap-2">
          <span class="text-sm text-muted-foreground">승인할 역할</span>
          <Badge v-for="r in approval.requiredApprovers ?? []" :key="r" variant="secondary">{{ ROLE_TITLES[r] ?? r }}</Badge>
        </CardContent>
        <CardFooter class="justify-end">
          <Button as-child class="w-full sm:w-auto">
            <RouterLink :to="`/proposals/${approval.proposalId}`">
              변경안 {{ ver(approval.versionNo) }} 승인 현황 보기
            </RouterLink>
          </Button>
        </CardFooter>
      </Card>

      <Card
        v-if="result"
        :class="{
          'ring-destructive/40': result.type === 'FAILED',
          'ring-warning/60': result.type === 'NEEDS_HUMAN'
        }"
      >
        <template v-if="result.type === 'DONE'">
          <CardHeader>
            <CardTitle>작업 완료</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-4">
            <p v-if="result.answer && result.answer.trim() !== tokenText.trim()" class="leading-relaxed whitespace-pre-wrap">{{ result.answer }}</p>
            <div class="flex flex-wrap gap-2">
              <Button v-if="result.callsheetVersionNo" as-child size="sm">
                <RouterLink to="/board">확정 콜시트 {{ ver(result.callsheetVersionNo) }} 보기</RouterLink>
              </Button>
              <Button v-if="result.proposalId" as-child size="sm" variant="outline">
                <RouterLink :to="`/proposals/${result.proposalId}`">변경안 보기</RouterLink>
              </Button>
              <Button v-if="result.traceUrl" as-child size="sm" variant="outline">
                <a :href="result.traceUrl" target="_blank" rel="noopener">추적 기록<ExternalLink data-icon="inline-end" /></a>
              </Button>
            </div>
            <template v-if="result.metrics">
              <Separator />
              <dl class="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
                <div v-for="[key, label] in METRIC_LABELS" :key="key" class="flex flex-col gap-0.5">
                  <dt class="text-xs text-muted-foreground">{{ label }}</dt>
                  <dd class="mono">{{ metricValue(key, result.metrics[key]) }}</dd>
                </div>
              </dl>
            </template>
            <template v-if="result.sources?.length">
              <Separator />
              <div class="flex flex-col gap-2">
                <h3 class="text-sm font-medium">출처</h3>
                <ul class="flex list-disc flex-col gap-1.5 pl-5 text-sm">
                  <li v-for="s in result.sources" :key="s.docId" class="min-w-0">
                    {{ s.title }} <span class="mono text-muted-foreground">{{ s.docId }}</span>
                    <p v-if="s.snippet" class="text-muted-foreground">{{ s.snippet }}</p>
                  </li>
                </ul>
              </div>
            </template>
          </CardContent>
        </template>

        <template v-else-if="result.type === 'FAILED'">
          <CardHeader>
            <CardTitle class="text-destructive">작업 실패</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col items-start gap-2">
            <p class="break-words">{{ result.error }}</p>
            <Button v-if="result.traceUrl" as-child variant="link" class="h-auto px-0">
              <a :href="result.traceUrl" target="_blank" rel="noopener">추적 기록 보기<ExternalLink data-icon="inline-end" /></a>
            </Button>
          </CardContent>
        </template>

        <template v-else>
          <CardHeader>
            <CardTitle>사람 확인 필요</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-4">
            <dl class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-2">
              <dt class="text-sm text-muted-foreground">멈춘 이유</dt>
              <dd class="break-words">{{ result.reason }}</dd>
              <template v-if="result.stopCondition">
                <dt class="text-sm text-muted-foreground">멈춘 조건</dt>
                <dd class="mono break-words">{{ result.stopCondition }}</dd>
              </template>
              <template v-if="result.best">
                <dt class="text-sm text-muted-foreground">가장 가까운 후보</dt>
                <dd class="break-words">{{ describeCandidate(result.best) }}</dd>
              </template>
            </dl>
            <div v-if="result.violations?.length" class="flex flex-col gap-2">
              <h3 class="text-sm font-medium">남은 위반</h3>
              <ul class="flex list-disc flex-col gap-1.5 pl-5 text-sm">
                <li v-for="(v, i) in result.violations" :key="i">{{ describeViolation(v) }}</li>
              </ul>
            </div>
            <div v-if="result.suggestions?.length" class="flex flex-col gap-2">
              <h3 class="text-sm font-medium">4안 추천 장소</h3>
              <ul class="flex flex-col divide-y divide-border rounded-lg border border-border">
                <li
                  v-for="(s, i) in result.suggestions.map(describeSuggestion)"
                  :key="i"
                  class="flex flex-col items-start gap-1 px-3 py-2.5"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-medium">{{ s.title }}</span>
                    <Badge v-if="s.mock" variant="secondary">외부 장소 후보</Badge>
                  </div>
                  <span v-if="s.meta.length" class="text-sm text-muted-foreground">{{ s.meta.join(' / ') }}</span>
                  <span v-if="s.reason" class="text-sm">{{ s.reason }}</span>
                </li>
              </ul>
            </div>
          </CardContent>
        </template>
      </Card>

      <Card v-if="tokenText">
        <CardHeader>
          <CardTitle>Agent 설명</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="leading-relaxed whitespace-pre-wrap">{{ tokenText }}<span v-if="isLive" class="ml-0.5 inline-block h-[1em] w-2 animate-pulse bg-foreground align-text-bottom"></span></p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>진행 기록</CardTitle>
          <CardAction class="mono text-sm text-muted-foreground">
            {{ timeline.filter((n) => n.status === 'done').length }}/{{ timeline.length }}
          </CardAction>
          <Progress
            class="col-span-full mt-2 h-1.5"
            :model-value="timeline.length ? (timeline.filter((n) => n.status === 'done').length / timeline.length) * 100 : 0"
          />
        </CardHeader>
        <CardContent>
          <!-- 기본은 단계 변화만 보이고, 도구 호출까지 담긴 시간순 기록은 전체 기록에서 본다 -->
          <Tabs default-value="steps" class="gap-4">
            <TabsList>
              <TabsTrigger value="steps">주요 단계</TabsTrigger>
              <TabsTrigger value="all">전체 기록 {{ log.length }}건</TabsTrigger>
            </TabsList>

            <TabsContent value="steps">
              <ol class="flex flex-col">
                <li v-for="(n, i) in timeline" :key="n.id" class="relative flex gap-3 pb-5 last:pb-0">
                  <!-- 다음 단계로 이어지는 세로선. 끝난 단계까지는 진하게 칠한다 -->
                  <span
                    v-if="i < timeline.length - 1"
                    aria-hidden="true"
                    class="absolute top-7 bottom-1 left-[11px] w-0.5 rounded-full"
                    :class="n.status === 'done' ? 'bg-primary' : 'bg-border'"
                  ></span>
                  <span
                    class="relative flex size-6 shrink-0 items-center justify-center rounded-full border-2"
                    :class="{
                      'border-primary bg-primary text-primary-foreground': n.status === 'done',
                      'border-primary bg-background': n.status === 'running',
                      'border-destructive bg-destructive text-primary-foreground': n.status === 'failed',
                      'border-border bg-background text-muted-foreground': n.status === 'pending'
                    }"
                  >
                    <Check v-if="n.status === 'done'" class="size-3.5" />
                    <X v-else-if="n.status === 'failed'" class="size-3.5" />
                    <span v-else-if="n.status === 'running'" class="size-2 animate-pulse rounded-full bg-primary"></span>
                    <span v-else class="mono text-[11px]">{{ i + 1 }}</span>
                  </span>
                  <div class="flex min-w-0 flex-1 flex-col gap-1 pt-0.5">
                    <div class="flex flex-wrap items-center gap-2">
                      <span :class="n.status === 'pending' ? 'text-muted-foreground' : 'font-medium'">{{ n.label }}</span>
                      <Badge v-if="n.loop" variant="secondary">루프 {{ n.loop }}</Badge>
                      <Badge v-if="n.status === 'running'" variant="info">진행 중</Badge>
                      <Badge v-else-if="n.status === 'failed'" variant="destructive">중단</Badge>
                    </div>
                    <p v-if="n.detail" class="text-sm break-words text-muted-foreground">{{ n.detail }}</p>
                  </div>
                </li>
              </ol>
            </TabsContent>

            <TabsContent value="all">
              <ol v-if="log.length" class="flex max-h-[640px] flex-col overflow-y-auto">
                <li
                  v-for="(e, i) in log"
                  :key="i"
                  class="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2 border-b border-border py-2 last:border-b-0"
                >
                  <span class="mono pt-0.5 text-xs text-muted-foreground">{{ i + 1 }}</span>
                  <div v-if="e.kind === 'node'" class="flex min-w-0 flex-col gap-0.5">
                    <div class="flex flex-wrap items-center gap-2 text-sm">
                      <span :class="e.end ? 'font-medium' : 'text-muted-foreground'">{{ e.label }} {{ e.end ? '완료' : '시작' }}</span>
                      <span v-if="e.loop" class="text-xs text-muted-foreground">루프 {{ e.loop }}</span>
                    </div>
                    <p v-if="e.detail" class="text-sm break-words text-muted-foreground">{{ e.detail }}</p>
                  </div>
                  <div v-else-if="e.kind === 'tool'" class="flex min-w-0 flex-col gap-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <Badge :variant="!e.done ? 'info' : e.ok === false ? 'destructive' : 'outline'">
                        <Spinner v-if="!e.done" data-icon="inline-start" />
                        {{ !e.done ? '호출 중' : e.ok === false ? '실패' : '도구' }}
                      </Badge>
                      <span class="mono min-w-0 text-sm break-all">{{ e.tool }}</span>
                      <span v-if="e.server" class="text-xs text-muted-foreground">{{ e.server === 'rag' ? 'RAG' : '업무' }} MCP</span>
                      <span v-if="e.ms !== undefined" class="mono text-xs text-muted-foreground">{{ e.ms }}ms</span>
                    </div>
                    <p v-if="e.args" class="mono truncate text-xs" :title="short(e.args)">{{ short(e.args) }}</p>
                    <p v-if="e.preview" class="truncate text-xs text-muted-foreground" :title="short(e.preview)">{{ short(e.preview) }}</p>
                  </div>
                  <div v-else class="flex items-center">
                    <Badge :variant="e.tone">{{ e.text }}</Badge>
                  </div>
                </li>
              </ol>
              <p v-else class="text-sm text-muted-foreground">아직 기록이 없습니다.</p>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
