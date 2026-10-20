<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { openStream } from '../sse.js'
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
const tokenText = ref('')
const approval = ref(null)
const result = ref(null)
const connection = ref('')
let source = null

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
  tokenText.value = ''
  approval.value = null
  result.value = null
  connection.value = ''
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
    if ((p.loop ?? 0) > loop.value) loop.value = p.loop
    if (!result.value) status.value = 'RUNNING'
  },
  TOOL_START(p) {
    tools.value.push({ tool: p.tool, server: p.server, args: p.args, done: false })
  },
  TOOL_END(p) {
    const open = [...tools.value].reverse().find((t) => t.tool === p.tool && !t.done)
    const entry = open ?? { tool: p.tool, server: '', args: null }
    Object.assign(entry, { done: true, ok: p.ok, ms: p.ms, preview: p.preview })
    if (!open) tools.value.push(entry)
  },
  TOKEN(p) {
    tokenText.value += p.text ?? ''
  },
  APPROVAL_REQUIRED(p) {
    approval.value = p
    status.value = 'WAITING_APPROVAL'
  },
  DONE(p) {
    result.value = { type: 'DONE', ...p }
    status.value = 'DONE'
  },
  FAILED(p) {
    result.value = { type: 'FAILED', ...p }
    status.value = 'FAILED'
    for (const n of Object.values(nodes)) if (n.status === 'running') n.status = 'failed'
  },
  NEEDS_HUMAN(p) {
    result.value = { type: 'NEEDS_HUMAN', ...p }
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
    return
  }
  // 응답을 기다리는 사이 다른 작업으로 이동했다면 이전 작업의 스트림을 열지 않는다.
  if (route.params.id !== id) return
  source = openStream(`/ai/tasks/${id}/stream`, handlers, {
    onStateChange: (s) => (connection.value = s)
  })
}

watch(() => route.params.id, (id) => id && start(id), { immediate: true })
onBeforeUnmount(() => source?.close())

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
    <div class="page-head">
      <div>
        <p class="eyebrow">Agent 작업 #{{ route.params.id }}</p>
        <h1 class="page-title">{{ KIND_LABELS[task?.kind] ?? 'Agent' }} 진행</h1>
        <p v-if="task?.question" class="page-sub">{{ task.question }}</p>
        <p v-else-if="task?.createdAt" class="page-sub">{{ dateTime(task.createdAt) }} 접수</p>
      </div>
      <div class="row">
        <span v-if="loop" class="badge tone-run">루프 {{ loop }}</span>
        <StatusBadge v-if="status" :status="status" />
      </div>
    </div>

    <div class="card live">
      <span class="dot" :class="{ on: isLive }"></span>
      <span v-if="activity && isLive">{{ activity }}</span>
      <span v-else-if="result" class="muted">작업이 끝났습니다.</span>
      <span v-else-if="status === 'WAITING_APPROVAL'" class="muted">승인 결과를 기다리는 중입니다.</span>
      <span v-else class="muted">Agent 이벤트를 기다리는 중입니다.</span>
      <span v-if="connection === 'reconnecting'" class="badge tone-stale">재연결 중</span>
      <span v-else-if="connection === 'closed' && !result" class="badge tone-bad">연결 끊김</span>
    </div>

    <section v-if="approval" class="card approval">
      <div>
        <p class="eyebrow">승인 요청</p>
        <h2 class="card-title">변경안 {{ ver(approval.versionNo) }} 승인 대기</h2>
        <p v-if="approval.summary">{{ approval.summary }}</p>
        <div class="row approvers">
          <span v-for="r in approval.requiredApprovers ?? []" :key="r" class="badge tone-wait">{{ ROLE_TITLES[r] ?? r }}</span>
        </div>
      </div>
      <RouterLink :to="`/proposals/${approval.proposalId}`" class="btn btn-primary">
        변경안 {{ ver(approval.versionNo) }} 승인 현황 보기
      </RouterLink>
    </section>

    <section v-if="result" class="card result" :class="result.type">
      <template v-if="result.type === 'DONE'">
        <h2 class="card-title">작업 완료 <StatusBadge status="DONE" /></h2>
        <p v-if="result.answer && result.answer.trim() !== tokenText.trim()" class="answer">{{ result.answer }}</p>
        <div class="row links">
          <RouterLink v-if="result.callsheetVersionNo" to="/" class="btn btn-primary btn-sm">
            확정 콜시트 {{ ver(result.callsheetVersionNo) }} 보기
          </RouterLink>
          <RouterLink v-if="result.proposalId" :to="`/proposals/${result.proposalId}`" class="btn btn-secondary btn-sm">
            변경안 보기
          </RouterLink>
          <a v-if="result.traceUrl" :href="result.traceUrl" target="_blank" rel="noopener" class="btn btn-secondary btn-sm">추적 기록</a>
        </div>
        <div v-if="result.metrics" class="metrics">
          <div v-for="[key, label] in METRIC_LABELS" :key="key" class="metric">
            <span class="muted small">{{ label }}</span>
            <strong>{{ metricValue(key, result.metrics[key]) }}</strong>
          </div>
        </div>
        <div v-if="result.sources?.length" class="sources">
          <p class="eyebrow">출처</p>
          <ul>
            <li v-for="s in result.sources" :key="s.docId">
              <strong>{{ s.title }}</strong> <span class="mono muted">{{ s.docId }}</span>
              <p v-if="s.snippet" class="muted small">{{ s.snippet }}</p>
            </li>
          </ul>
        </div>
      </template>

      <template v-else-if="result.type === 'FAILED'">
        <h2 class="card-title">작업 실패 <StatusBadge status="FAILED" /></h2>
        <p>{{ result.error }}</p>
        <a v-if="result.traceUrl" :href="result.traceUrl" target="_blank" rel="noopener" class="link">추적 기록 보기</a>
      </template>

      <template v-else>
        <h2 class="card-title">사람 확인 필요 <StatusBadge status="NEEDS_HUMAN" /></h2>
        <dl class="facts">
          <dt>멈춘 이유</dt>
          <dd>{{ result.reason }}</dd>
          <template v-if="result.stopCondition">
            <dt>멈춘 조건</dt>
            <dd class="mono">{{ result.stopCondition }}</dd>
          </template>
          <template v-if="result.best">
            <dt>가장 가까운 후보</dt>
            <dd>{{ describeCandidate(result.best) }}</dd>
          </template>
        </dl>
        <div v-if="result.violations?.length" class="stack-sm">
          <p class="eyebrow">남은 위반</p>
          <ul class="plain">
            <li v-for="(v, i) in result.violations" :key="i">{{ describeViolation(v) }}</li>
          </ul>
        </div>
        <div v-if="result.suggestions?.length" class="stack-sm">
          <p class="eyebrow">4안 추천</p>
          <div class="suggestions">
            <div v-for="(s, i) in result.suggestions.map(describeSuggestion)" :key="i" class="suggestion">
              <strong>{{ s.title }}</strong>
              <span v-if="s.meta.length" class="muted small">{{ s.meta.join(' / ') }}</span>
              <span v-if="s.reason" class="small">{{ s.reason }}</span>
              <span v-if="s.mock" class="badge tone-wait">외부 장소 후보</span>
            </div>
          </div>
        </div>
      </template>
    </section>

    <section v-if="tokenText" class="card">
      <h2 class="card-title">Agent 설명</h2>
      <p class="answer">{{ tokenText }}<span v-if="isLive" class="caret"></span></p>
    </section>

    <div class="grid-2">
      <section class="card">
        <h2 class="card-title">단계 타임라인</h2>
        <ol class="timeline">
          <li v-for="n in timeline" :key="n.id" :class="n.status">
            <span class="marker"></span>
            <div class="node-body">
              <div class="row">
                <strong>{{ n.label }}</strong>
                <span v-if="n.loop" class="badge tone-wait">루프 {{ n.loop }}</span>
                <span v-if="n.status === 'running'" class="badge tone-run">진행 중</span>
                <span v-else-if="n.status === 'failed'" class="badge tone-bad">중단</span>
              </div>
              <p v-if="n.detail" class="muted small">{{ n.detail }}</p>
            </div>
          </li>
        </ol>
      </section>

      <section class="card">
        <h2 class="card-title">도구 호출 로그 <span class="muted small">{{ tools.length }}건</span></h2>
        <ul v-if="tools.length" class="tools">
          <li v-for="(t, i) in tools" :key="i">
            <div class="row">
              <span class="badge" :class="!t.done ? 'tone-run' : t.ok === false ? 'tone-bad' : 'tone-ok'">
                {{ !t.done ? '호출 중' : t.ok === false ? '실패' : '완료' }}
              </span>
              <strong class="mono">{{ t.tool }}</strong>
              <span v-if="t.server" class="muted small">{{ t.server === 'rag' ? 'RAG' : '업무' }} MCP</span>
              <span v-if="t.ms !== undefined" class="muted small">{{ t.ms }}ms</span>
            </div>
            <p v-if="t.args" class="mono clip" :title="short(t.args)">{{ short(t.args) }}</p>
            <p v-if="t.preview" class="small muted clip" :title="short(t.preview)">{{ short(t.preview) }}</p>
          </li>
        </ul>
        <p v-else class="empty">아직 호출한 도구가 없습니다.</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.live {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 16px 20px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-faint);
}

.dot.on {
  background: var(--mint);
  box-shadow: 0 0 0 0 rgba(60, 230, 211, 0.6);
  animation: pulse 1.6s infinite;
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 10px rgba(60, 230, 211, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(60, 230, 211, 0);
  }
}

.approval {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  border: 2px solid var(--mint);
}

.approval .card-title {
  margin-bottom: 6px;
}

.approvers {
  margin-top: 10px;
}

.result.DONE {
  border-top: 4px solid var(--ok);
}

.result.FAILED {
  border-top: 4px solid var(--bad);
}

.result.NEEDS_HUMAN {
  border-top: 4px solid var(--stale);
}

.answer {
  white-space: pre-wrap;
  line-height: 1.7;
}

.links {
  margin: 14px 0;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.metric {
  background: var(--head-bg);
  border-radius: 12px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
}

.metric strong {
  font-size: 18px;
}

.sources {
  margin-top: 18px;
}

.sources ul,
.plain {
  margin: 6px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px 16px;
  margin: 0 0 14px;
}

.facts dt {
  color: var(--text-sub);
  font-weight: 700;
  font-size: 13px;
}

.facts dd {
  margin: 0;
}

.stack-sm {
  margin-top: 14px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.suggestion {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline li {
  position: relative;
  display: flex;
  gap: 14px;
  padding-bottom: 18px;
}

.timeline li:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 20px;
  bottom: 0;
  width: 2px;
  background: var(--line);
}

.timeline li.done:not(:last-child)::before {
  background: var(--charcoal);
}

.marker {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: 50%;
  border: 2px solid var(--line);
  background: #fff;
}

.done .marker {
  border-color: var(--charcoal);
  background: var(--charcoal);
  box-shadow: inset 0 0 0 4px var(--charcoal), inset 0 0 0 9px var(--mint);
}

.running .marker {
  border-color: var(--mint);
  background: var(--mint);
  animation: pulse 1.6s infinite;
}

.failed .marker {
  border-color: var(--bad);
  background: var(--bad);
}

.pending .node-body strong {
  color: var(--text-faint);
}

.node-body {
  min-width: 0;
}

.tools {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 560px;
  overflow-y: auto;
}

.tools li {
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
  min-width: 0;
}

.clip {
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .approval .btn {
    width: 100%;
  }
}
</style>
