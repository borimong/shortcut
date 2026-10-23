<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AskBox from '../components/AskBox.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { useAuthStore } from '../stores/auth.js'
import { useNotificationStore } from '../stores/notifications.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime, signedWon, ver, won } from '../format.js'
import { CONSTRAINT_LABELS, DEPARTMENTS, ISSUE_LABELS, ISSUE_OPTIONS, REVIEW_ACTIONS, REVIEW_LABELS, SCORE_LABELS } from '../labels.js'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, EmptyDescription, EmptyMedia } from '@/components/ui/empty'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()
const toast = useToastStore()

const proposal = ref(null)
const error = ref(null)
const evidence = ref(null)
const rejecting = ref(false)
const reason = ref('')
const deciding = ref(false)
const issues = ref([])
const task = ref(null)
const priorRejections = ref([])
let followTimer = null

// backend와 같은 기준이다. "ㅇ" 같은 사유로는 Agent가 무엇을 고칠지 알 수 없어 지나치게 넓게 제외하게 된다.
const MIN_REASON = 5
const canReject = computed(() => reason.value.trim().length >= MIN_REASON && issues.value.length > 0)

const nextProposalId = computed(() => {
  const t = task.value
  return t?.proposalId && String(t.proposalId) !== String(proposal.value?.id) ? t.proposalId : null
})

function toggleIssue(value) {
  issues.value = issues.value.includes(value) ? issues.value.filter((v) => v !== value) : [...issues.value, value]
}

function issueText(list) {
  return (list ?? []).map((i) => ISSUE_LABELS[i] ?? i).join(', ')
}

async function loadContext() {
  const p = proposal.value
  if (!p) return
  try {
    task.value = await api(`/ai/tasks/${p.taskId}`)
  } catch {
    task.value = null
  }
  if (p.loopNo <= 1) {
    priorRejections.value = []
    return
  }
  // 앞선 거절안은 촬영판이 지금 보는 날이 아니라 이 변경안의 촬영일에서 찾는다.
  const list = await api(`/proposals?shootDayId=${p.shootDayId}`)
  const earlier = list
    .filter((x) => x.taskId === p.taskId && x.id !== p.id && x.status === 'REJECTED' && x.loopNo < p.loopNo)
    .sort((a, b) => a.loopNo - b.loopNo)
  priorRejections.value = await Promise.all(
    earlier.map(async (x) => {
      const detail = await api(`/proposals/${x.id}`)
      return {
        id: x.id,
        loopNo: x.loopNo,
        plan: `${detail.proposed?.location?.name ?? ''} ${detail.proposed?.start ?? ''}~${detail.proposed?.end ?? ''}`,
        rejection: (detail.approvals ?? []).find((a) => a.status === 'REJECTED') ?? null
      }
    })
  )
}

// 거절된 안을 보고 있는 동안 새 안이 나오거나 작업이 끝날 때까지 작업 상태를 따라간다.
function followReplan() {
  clearInterval(followTimer)
  followTimer = null
  if (proposal.value?.status !== 'REJECTED' || nextProposalId.value) return
  if (['DONE', 'FAILED', 'NEEDS_HUMAN'].includes(task.value?.status)) return
  followTimer = setInterval(async () => {
    await loadContext()
    if (nextProposalId.value || ['DONE', 'FAILED', 'NEEDS_HUMAN'].includes(task.value?.status)) {
      clearInterval(followTimer)
      followTimer = null
    }
  }, 3000)
}

async function load() {
  try {
    proposal.value = await api(`/proposals/${route.params.id}`)
    error.value = null
    await loadContext()
    followReplan()
  } catch (e) {
    error.value = e
  }
}

watch(() => route.params.id, (id) => id && load(), { immediate: true })

watch(
  () => notifications.lastApprovalUpdate,
  (u) => {
    if (u && String(u.proposalId) === String(route.params.id)) load()
  }
)

function names(list) {
  return (list ?? []).map((e) => e.name).join(', ')
}

function sameIds(a, b) {
  const ids = (list) => (list ?? []).map((e) => e.id).sort().join(',')
  return ids(a) === ids(b)
}

const diffRows = computed(() => {
  const p = proposal.value
  if (!p) return []
  const o = p.original ?? {}
  const n = p.proposed ?? {}
  const src = n.source ?? {}
  const km = p.distanceDeltaKm ?? 0
  return [
    {
      label: '장소',
      from: o.location?.name,
      to: `${n.location?.name ?? ''}${n.location ? (n.location.indoor ? ' (실내)' : ' (야외)') : ''}`,
      source: src.location,
      changed: o.location?.id !== n.location?.id
    },
    { label: '장비', from: names(o.equipment), to: names(n.equipment), source: src.equipment, changed: !sameIds(o.equipment, n.equipment) },
    {
      label: '시간대',
      from: `${o.start}~${o.end}`,
      to: `${n.start}~${n.end}`,
      source: src.time,
      changed: o.start !== n.start || o.end !== n.end
    },
    { label: '비용', from: won(o.cost), to: `${won(n.cost)} (${signedWon(p.extraCost ?? 0)})`, changed: (p.extraCost ?? 0) !== 0 },
    { label: '이동거리', from: '현재 장소 기준', to: `${km > 0 ? '+' : ''}${km}km`, changed: km !== 0 }
  ]
})

// 스트립보드 관례대로 실내/야외와 낮/밤을 띠 색으로 구분한다. 18시 이후 시작은 밤 촬영으로 본다.
const STRIPS = {
  'INT-D': { label: '실내 낮', class: 'border-border bg-card text-foreground' },
  'EXT-D': { label: '야외 낮', class: 'border-transparent bg-strip-ext-day text-foreground' },
  'INT-N': { label: '실내 밤', class: 'border-transparent bg-strip-int-night text-primary-foreground' },
  'EXT-N': { label: '야외 밤', class: 'border-transparent bg-strip-ext-night text-primary-foreground' }
}

function toMinutes(hhmm) {
  const [h, m] = String(hhmm ?? '').split(':').map(Number)
  return h * 60 + (m || 0)
}

const strips = computed(() => {
  const p = proposal.value
  if (!p?.original?.start || !p?.proposed?.start) return null
  const rows = [
    ['현재 확정', p.original],
    ['변경안', p.proposed]
  ].map(([label, plan]) => {
    const start = toMinutes(plan.start)
    const end = toMinutes(plan.end)
    const key = `${plan.location?.indoor ? 'INT' : 'EXT'}-${start >= 18 * 60 ? 'N' : 'D'}`
    return { label, plan, start, end, strip: STRIPS[key] }
  })
  // 두 안을 모두 담고 앞뒤로 한 시간씩 여유를 둔다
  const lo = Math.floor(Math.min(...rows.map((r) => r.start)) / 60) * 60 - 60
  const hi = Math.ceil(Math.max(...rows.map((r) => r.end)) / 60) * 60 + 60
  const place = (start, end) => ({ left: `${((start - lo) / (hi - lo)) * 100}%`, width: `${((end - start) / (hi - lo)) * 100}%` })
  const hours = []
  for (let m = lo; m <= hi; m += 60) hours.push({ label: String(m / 60).padStart(2, '0'), left: `${((m - lo) / (hi - lo)) * 100}%` })
  return {
    hours,
    rows: rows.map((r) => ({ ...r, style: place(r.start, r.end) })),
    ghost: place(rows[0].start, rows[0].end),
    moved: rows[0].start !== rows[1].start || rows[0].end !== rows[1].end
  }
})

const scoreRows = computed(() => {
  const p = proposal.value
  if (!p?.scoreBreakdown) return []
  return Object.entries(p.scoreBreakdown).map(([key, value]) => ({
    key,
    label: SCORE_LABELS[key] ?? key,
    value: Number(value),
    weight: p.weights?.[key]
  }))
})

// 승인 요청에 실린 안의 회차 점수를 항목별로 보여 준다. 5회 도달로 넘어온 경우 가장 높았던 회차다.
const review = computed(() => {
  const r = proposal.value?.review
  if (!r?.history?.length) return null
  const chosen = r.history.find((h) => h.round === r.chosenRound) ?? r.history[r.history.length - 1]
  return {
    ...r,
    rows: Object.entries(chosen.breakdown ?? {}).map(([key, value]) => ({ key, label: REVIEW_LABELS[key] ?? key, value }))
  }
})

const progress = computed(() => {
  const p = proposal.value
  if (!p?.requiredCount) return 0
  return Math.round((p.approvedCount / p.requiredCount) * 100)
})

const APPROVAL_FILTERS = [
  { value: 'ALL', label: '전체' },
  { value: 'PENDING', label: '대기' },
  { value: 'APPROVED', label: '승인' },
  { value: 'REJECTED', label: '거절' }
]
const approvalFilter = ref('ALL')

function countApprovals(status) {
  const list = proposal.value?.approvals ?? []
  return status === 'ALL' ? list.length : list.filter((a) => a.status === status).length
}

// 사람 한 줄, 상태 한 열로 보여 주되 부서별로 묶어 어느 부서가 남았는지 바로 보이게 한다.
const approvalGroups = computed(() => {
  const list = proposal.value?.approvals ?? []
  const known = new Set(DEPARTMENTS.flatMap((d) => d.roles))
  const groups = [...DEPARTMENTS, { name: '기타', roles: list.map((a) => a.role).filter((r) => !known.has(r)) }]
  return groups
    .map((d) => {
      const members = list.filter((a) => d.roles.includes(a.role))
      return {
        name: d.name,
        total: members.length,
        approved: members.filter((a) => a.status === 'APPROVED').length,
        rows: members.filter((a) => approvalFilter.value === 'ALL' || a.status === approvalFilter.value)
      }
    })
    .filter((g) => g.rows.length)
})

const myPending = computed(() => {
  const p = proposal.value
  if (!p || p.status !== 'PENDING') return null
  return (p.approvals ?? []).find((a) => a.role === auth.user?.role && a.status === 'PENDING') ?? null
})

function openEvidence(id) {
  const found = (proposal.value?.evidence ?? []).find((e) => e.id === id || e.docId === id)
  evidence.value = found ?? { id, title: id, text: '이 근거의 원문을 변경안에서 찾지 못했습니다.' }
}

async function decide(decision) {
  if (decision === 'REJECT' && !canReject.value) return
  deciding.value = true
  try {
    const body = { proposalId: proposal.value.id, decision }
    if (decision === 'REJECT') {
      body.reason = reason.value.trim()
      body.issues = issues.value
    }
    await api(`/ai/tasks/${proposal.value.taskId}/approval`, { method: 'POST', body })
    rejecting.value = false
    reason.value = ''
    issues.value = []
    if (decision === 'REJECT') {
      toast.info('거절했습니다. Agent가 사유를 보완한 새 계획안을 만듭니다.')
      // 거절 직후에는 재계획이 진행되는 화면을 보여 줘야 거절이 다음 루프로 이어지는 것이 보인다.
      router.push(`/tasks/${proposal.value.taskId}`)
      return
    }
    toast.info('승인했습니다.')
    await load()
  } catch (e) {
    toast.error(e)
  } finally {
    deciding.value = false
  }
}

function onKey(e) {
  if (e.key === 'Escape') evidence.value = null
}

onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  clearInterval(followTimer)
})
</script>

<template>
  <div class="page">
    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>

    <template v-if="proposal">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div class="flex min-w-0 flex-col gap-1">
          <h1 class="page-title">변경안 {{ ver(proposal.versionNo) }}</h1>
          <p class="text-sm text-muted-foreground">
            <span class="mono">#{{ proposal.id }}</span>, 루프 {{ proposal.loopNo }}, {{ dateTime(proposal.createdAt) }} 생성, 데이터 버전 {{ proposal.dataVersion }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <StatusBadge :status="proposal.status" />
          <Button as-child variant="outline" size="sm">
            <RouterLink :to="`/tasks/${proposal.taskId}`">Agent 진행 보기</RouterLink>
          </Button>
        </div>
      </div>

      <Alert v-if="proposal.status === 'REJECTED'" class="flex flex-wrap items-center justify-between gap-3 border-primary/50">
        <template v-if="nextProposalId">
          <span>거절 사유를 반영한 새 변경안이 나왔습니다.</span>
          <Button as-child size="sm">
            <RouterLink :to="`/proposals/${nextProposalId}`">새 변경안 보기</RouterLink>
          </Button>
        </template>
        <template v-else-if="task?.status === 'NEEDS_HUMAN'">
          <span>더 짤 수 있는 안이 없어 사람이 확인하도록 넘겼습니다. 멈춘 이유와 추천 장소는 진행 화면에 있습니다.</span>
          <Button as-child variant="outline" size="sm">
            <RouterLink :to="`/tasks/${proposal.taskId}`">진행 보기</RouterLink>
          </Button>
        </template>
        <template v-else>
          <span>거절 사유를 반영해 새 계획안을 만들고 있습니다.</span>
          <Button as-child variant="outline" size="sm">
            <RouterLink :to="`/tasks/${proposal.taskId}`">진행 보기</RouterLink>
          </Button>
        </template>
      </Alert>

      <Alert v-if="proposal.status === 'STALE'" class="border-warning/40 bg-warning/20 text-warning-foreground">
        <AlertDescription class="text-warning-foreground">승인을 기다리는 사이 촬영 데이터가 바뀌어 이 변경안은 확정할 수 없습니다.</AlertDescription>
      </Alert>

      <Card v-if="priorRejections.length">
        <CardHeader>
          <CardTitle>반영한 거절 사유</CardTitle>
          <CardDescription>앞선 안이 거절돼 루프 {{ proposal.loopNo }}에서 다시 짠 안입니다. 거절할 때 고른 항목만 바꾸고 나머지는 되도록 그대로 뒀습니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul class="flex flex-col">
            <li
              v-for="r in priorRejections"
              :key="r.id"
              class="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border py-2.5 first:pt-0 last:border-b-0 last:pb-0"
            >
              <RouterLink :to="`/proposals/${r.id}`" class="mono underline underline-offset-3">루프 {{ r.loopNo }}</RouterLink>
              <span class="text-muted-foreground">{{ r.plan }}</span>
              <template v-if="r.rejection">
                <span>{{ r.rejection.title }} 거절</span>
                <Badge v-if="r.rejection.issues?.length" variant="destructive">{{ issueText(r.rejection.issues) }}</Badge>
                <span class="basis-full text-muted-foreground">"{{ r.rejection.reason }}"</span>
              </template>
            </li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>원본 대비 변경</CardTitle>
        </CardHeader>
        <CardContent class="flex flex-col gap-4">
          <div v-if="strips" class="flex flex-col gap-1.5">
            <div class="grid grid-cols-[4.5rem_minmax(0,1fr)]">
              <span></span>
              <div class="mono relative h-4 text-[11px] text-muted-foreground">
                <!-- 양 끝 눈금은 띠 밖으로 넘치지 않게 안쪽으로 붙인다 -->
                <span
                  v-for="(h, k) in strips.hours"
                  :key="h.label"
                  :class="cn('absolute whitespace-nowrap', k === 0 ? '' : k === strips.hours.length - 1 ? '-translate-x-full' : '-translate-x-1/2')"
                  :style="{ left: h.left }"
                >{{ h.label }}시</span>
              </div>
            </div>
            <div v-for="(r, i) in strips.rows" :key="r.label" class="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center">
              <span class="text-sm text-muted-foreground">{{ r.label }}</span>
              <div class="relative h-11 rounded-md bg-muted/60">
                <span
                  v-for="h in strips.hours"
                  :key="h.label"
                  aria-hidden="true"
                  class="absolute inset-y-0 w-px bg-border"
                  :style="{ left: h.left }"
                ></span>
                <!-- 변경안 줄에 현재 확정 시간을 점선으로 겹쳐 얼마나 옮겼는지 보여 준다 -->
                <span
                  v-if="i === 1 && strips.moved"
                  aria-hidden="true"
                  class="absolute inset-y-1 rounded border border-dashed border-muted-foreground/60"
                  :style="strips.ghost"
                ></span>
                <div
                  :class="cn('absolute inset-y-1 flex min-w-0 flex-col justify-center rounded border px-2 leading-tight', r.strip.class)"
                  :style="r.style"
                  :title="`${r.strip.label}, ${r.plan.location?.name ?? ''}, ${r.plan.start}~${r.plan.end}`"
                >
                  <span class="truncate text-xs font-medium">{{ r.plan.location?.name }}</span>
                  <span class="truncate text-[11px] opacity-80">{{ r.strip.label }} {{ r.plan.start }}~{{ r.plan.end }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="overflow-hidden rounded-lg border border-border">
            <Table>
              <TableHeader class="bg-muted">
                <TableRow>
                  <TableHead>항목</TableHead>
                  <TableHead>현재 확정</TableHead>
                  <TableHead>변경안</TableHead>
                  <TableHead>출처</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="r in diffRows" :key="r.label">
                  <TableCell :class="r.changed ? 'border-l-2 border-l-primary' : 'text-muted-foreground'">{{ r.label }}</TableCell>
                  <TableCell class="text-muted-foreground">{{ r.from }}</TableCell>
                  <TableCell :class="r.changed ? 'font-semibold' : ''">{{ r.to }}</TableCell>
                  <TableCell>
                    <Badge v-if="r.source" variant="info">{{ r.source === 4 ? '4안 (대체 장소)' : `${r.source}안` }}</Badge>
                    <span v-else class="text-muted-foreground">계산값</span>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <p v-if="proposal.explanation" class="leading-relaxed whitespace-pre-wrap">{{ proposal.explanation }}</p>
        </CardContent>
      </Card>

      <Card v-if="review">
        <CardHeader>
          <CardTitle>자체 검토</CardTitle>
          <CardDescription>승인을 요청하기 전에 근거 개수, 엔진 값 대조, 설명 점검 질문으로 100점 만점 점수를 계산합니다. {{ review.threshold }}점이 안 되거나 통과를 막는 사유가 있으면 고쳐서 다시 검토합니다.</CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-5">
          <div class="flex flex-wrap items-baseline gap-1.5">
            <span class="text-3xl font-bold tracking-tight">{{ review.score }}</span>
            <span class="text-muted-foreground">/ 100</span>
            <Badge :variant="review.passed ? 'success' : 'warning'" class="ml-1">
              {{ review.passed ? `${review.rounds}회차 통과` : `${review.rounds}회 도달, ${review.chosenRound}회차 안으로 요청` }}
            </Badge>
          </div>
          <ul class="flex flex-col gap-3">
            <li v-for="r in review.rows" :key="r.key" class="flex flex-col gap-1">
              <div class="flex justify-between gap-2 text-sm">
                <span>{{ r.label }}</span>
                <span class="mono text-muted-foreground">{{ r.value }} / 20</span>
              </div>
              <Progress :model-value="(r.value / 20) * 100" class="h-1.5 *:data-[slot=progress-indicator]:bg-foreground/70" />
            </li>
          </ul>
          <Separator />
          <ol class="flex flex-col gap-2">
            <li
              v-for="h in review.history"
              :key="h.round"
              :class="cn(
                'flex flex-wrap items-baseline gap-x-2 gap-y-1 border-l-2 border-transparent pl-3 text-sm',
                h.round === review.chosenRound && 'border-primary'
              )"
            >
              <span class="mono text-muted-foreground">{{ h.round }}회차</span>
              <span class="mono">{{ h.score }}점</span>
              <span v-if="h.passed === false || h.score < review.threshold" class="text-muted-foreground">{{ REVIEW_ACTIONS[h.action] ?? h.action }}</span>
              <span class="basis-full">{{ (h.feedback ?? []).join(' ') }}</span>
            </li>
          </ol>
        </CardContent>
      </Card>

      <div class="grid gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>종합 점수</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-5">
            <div class="flex flex-col gap-2.5">
              <div class="flex items-baseline gap-1.5">
                <span class="mono text-3xl font-bold tracking-tight">{{ Number(proposal.score).toFixed(3) }}</span>
                <span class="text-muted-foreground">/ 1.000</span>
              </div>
              <Progress :model-value="Math.min(proposal.score, 1) * 100" class="h-2" />
            </div>
            <ul class="flex flex-col gap-3">
              <li v-for="s in scoreRows" :key="s.key" class="flex flex-col gap-1">
                <div class="flex justify-between gap-2 text-sm">
                  <span>
                    {{ s.label }}
                    <span v-if="s.weight !== undefined" class="text-muted-foreground">(가중치 {{ Math.round(s.weight * 100) }}%)</span>
                  </span>
                  <span class="mono">{{ s.value.toFixed(3) }}</span>
                </div>
                <Progress :model-value="Math.min(s.value, 1) * 100" class="h-1.5 *:data-[slot=progress-indicator]:bg-foreground/70" />
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>하드 제약 체크리스트</CardTitle>
          </CardHeader>
          <CardContent class="flex flex-col gap-4">
            <ul class="flex flex-col">
              <li
                v-for="c in proposal.checklist"
                :key="c.constraint"
                class="flex flex-col gap-1.5 border-b border-border py-3 first:pt-0 last:border-b-0 last:pb-0"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <StatusBadge :status="c.status" />
                  <span class="font-medium">{{ CONSTRAINT_LABELS[c.constraint] ?? c.constraint }}</span>
                </div>
                <p v-if="c.note" class="text-sm text-muted-foreground">{{ c.note }}</p>
                <div v-if="c.evidenceIds?.length" class="flex flex-wrap items-center gap-1.5">
                  <Button
                    v-for="id in c.evidenceIds"
                    :key="id"
                    type="button"
                    variant="outline"
                    size="xs"
                    class="mono"
                    @click="openEvidence(id)"
                  >
                    {{ id }}
                  </Button>
                </div>
              </li>
            </ul>
            <Separator />
            <div class="flex flex-col gap-1.5">
              <h3 class="text-sm font-medium">미확정 항목</h3>
              <ul v-if="proposal.unresolved?.length" class="list-disc pl-5 text-sm">
                <li v-for="(u, i) in proposal.unresolved" :key="i">{{ u }}</li>
              </ul>
              <p v-else class="text-sm text-muted-foreground">없습니다.</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>승인 현황</CardTitle>
          <CardAction>
            <span class="mono text-sm text-muted-foreground">{{ proposal.approvedCount }} / {{ proposal.requiredCount }} 완료</span>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-4">
          <Progress :model-value="progress" class="h-2" />
          <ToggleGroup
            v-model="approvalFilter"
            type="single"
            variant="outline"
            size="sm"
            class="flex-wrap"
            @update:model-value="(v) => { if (!v) approvalFilter = 'ALL' }"
          >
            <ToggleGroupItem v-for="f in APPROVAL_FILTERS" :key="f.value" :value="f.value">
              {{ f.label }} <span class="mono text-muted-foreground">{{ countApprovals(f.value) }}</span>
            </ToggleGroupItem>
          </ToggleGroup>
          <div class="overflow-hidden rounded-lg border border-border">
            <Table>
              <TableHeader class="bg-muted">
                <TableRow>
                  <TableHead>승인자</TableHead>
                  <TableHead>담당 범위</TableHead>
                  <TableHead>상태</TableHead>
                  <TableHead>처리 시각</TableHead>
                  <TableHead>거절 사유</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <template v-for="g in approvalGroups" :key="g.name">
                  <TableRow class="hover:bg-transparent">
                    <TableCell colspan="5" class="bg-muted/40 py-1.5 text-sm">
                      <span class="font-medium">{{ g.name }}</span>
                      <span class="ml-2 text-muted-foreground">{{ g.total }}명 중 {{ g.approved }}명 승인</span>
                    </TableCell>
                  </TableRow>
                  <TableRow
                    v-for="a in g.rows"
                    :key="a.role"
                    :class="{ 'bg-accent/60 hover:bg-accent/60': a.role === auth.user?.role }"
                  >
                    <TableCell>
                      <span class="font-medium">{{ a.title }}</span>
                      <span v-if="a.userName" class="block text-xs text-muted-foreground">{{ a.userName }}</span>
                    </TableCell>
                    <TableCell>{{ a.scope }}</TableCell>
                    <TableCell><StatusBadge :status="a.status" /></TableCell>
                    <TableCell class="mono" :title="a.decidedAt ? new Date(a.decidedAt).toLocaleString('ko-KR') : ''">
                      {{ a.decidedAt ? dateTime(a.decidedAt) : '' }}
                    </TableCell>
                    <TableCell class="min-w-45 whitespace-normal">
                      <Badge v-if="a.issues?.length" variant="destructive">{{ issueText(a.issues) }}</Badge>
                      {{ a.reason ?? '' }}
                    </TableCell>
                  </TableRow>
                </template>
                <TableRow v-if="!approvalGroups.length" class="hover:bg-transparent">
                  <TableCell colspan="5" class="py-6 text-center text-muted-foreground">해당하는 승인자가 없습니다.</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>

          <section v-if="myPending" class="flex flex-col gap-3 rounded-lg border border-primary p-4">
            <div class="flex flex-col gap-1">
              <h3 class="font-semibold">{{ myPending.title }} 승인 차례입니다</h3>
              <dl class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 text-sm">
                <dt class="text-muted-foreground">담당 범위</dt>
                <dd class="break-words">{{ myPending.scope }}</dd>
              </dl>
            </div>
            <div v-if="!rejecting" class="flex flex-wrap gap-2">
              <Button type="button" :disabled="deciding" @click="decide('APPROVE')">승인</Button>
              <Button type="button" variant="destructive" :disabled="deciding" @click="rejecting = true">거절</Button>
            </div>
            <FieldGroup v-else>
              <FieldSet>
                <FieldLegend variant="label">문제가 있는 항목</FieldLegend>
                <FieldDescription>하나 이상 골라야 하며, 고르지 않은 항목은 그대로 둡니다.</FieldDescription>
                <ToggleGroup
                  v-model="issues"
                  type="multiple"
                  variant="outline"
                  size="sm"
                  :spacing="2"
                  class="flex-wrap"
                >
                  <ToggleGroupItem
                    v-for="o in ISSUE_OPTIONS"
                    :key="o.value"
                    :value="o.value"
                    class="aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                  >
                    {{ o.label }}
                  </ToggleGroupItem>
                </ToggleGroup>
              </FieldSet>
              <Field>
                <FieldLabel for="reject-reason">거절 사유</FieldLabel>
                <Textarea
                  id="reject-reason"
                  v-model="reason"
                  placeholder="예: 성수 스튜디오는 오후 공사 소음 때문에 동시녹음이 어렵습니다."
                />
                <FieldDescription>{{ MIN_REASON }}자 이상 적어야 거절할 수 있습니다.</FieldDescription>
              </Field>
              <div class="flex flex-wrap gap-2">
                <Button type="button" variant="destructive" :disabled="deciding || !canReject" @click="decide('REJECT')">
                  거절하고 새 계획 요청
                </Button>
                <Button type="button" variant="outline" :disabled="deciding" @click="rejecting = false">취소</Button>
              </div>
            </FieldGroup>
          </section>
        </CardContent>
      </Card>

      <AskBox :proposal-id="proposal.id" />
    </template>

    <Empty v-else-if="!error" class="border">
      <EmptyMedia><Spinner /></EmptyMedia>
      <EmptyDescription>변경안을 불러오는 중입니다.</EmptyDescription>
    </Empty>

    <Dialog :open="!!evidence" @update:open="(open) => { if (!open) evidence = null }">
      <DialogContent
        :show-close-button="false"
        class="top-0 right-0 left-auto h-full max-h-none w-full max-w-[440px] translate-x-0 translate-y-0 content-start overflow-y-auto rounded-none p-6 sm:max-w-[440px] data-open:slide-in-from-right data-closed:slide-out-to-right"
      >
        <DialogHeader class="flex-row items-start justify-between gap-3">
          <div class="flex min-w-0 flex-col gap-1">
            <DialogTitle class="text-lg leading-snug">{{ evidence?.title }}</DialogTitle>
            <DialogDescription>
              <template v-if="evidence?.docType">{{ evidence.docType }} 근거, </template>
              <span class="mono">{{ evidence?.id }}<template v-if="evidence?.docId"> / {{ evidence.docId }}</template></span>
            </DialogDescription>
          </div>
          <Button type="button" variant="outline" size="sm" @click="evidence = null">닫기</Button>
        </DialogHeader>
        <p class="rounded-lg bg-muted p-4 text-sm leading-relaxed whitespace-pre-wrap">{{ evidence?.text }}</p>
      </DialogContent>
    </Dialog>
  </div>
</template>
