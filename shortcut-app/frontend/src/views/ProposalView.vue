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
import { CONSTRAINT_LABELS, ISSUE_LABELS, ISSUE_OPTIONS, REVIEW_ACTIONS, REVIEW_LABELS, SCORE_LABELS, SHOOT_DAY_ID } from '../labels.js'

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
  const list = await api(`/proposals?shootDayId=${SHOOT_DAY_ID}`)
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
    <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>

    <template v-if="proposal">
      <div class="page-head">
        <div>
          <p class="eyebrow">변경안 #{{ proposal.id }}, 루프 {{ proposal.loopNo }}</p>
          <h1 class="page-title">변경안 {{ ver(proposal.versionNo) }}</h1>
          <p class="page-sub">{{ dateTime(proposal.createdAt) }} 생성, 데이터 버전 {{ proposal.dataVersion }}</p>
        </div>
        <div class="row">
          <RouterLink :to="`/tasks/${proposal.taskId}`" class="btn btn-secondary btn-sm">Agent 진행 보기</RouterLink>
          <StatusBadge :status="proposal.status" />
        </div>
      </div>

      <div v-if="proposal.status === 'REJECTED'" class="replan-note">
        <template v-if="nextProposalId">
          <span>거절 사유를 보완한 새 변경안이 나왔습니다.</span>
          <RouterLink :to="`/proposals/${nextProposalId}`" class="btn btn-primary btn-sm">새 변경안 보기</RouterLink>
        </template>
        <template v-else-if="task?.status === 'NEEDS_HUMAN'">
          <span>더 짤 수 있는 안이 없어 사람에게 넘겼습니다. 진행 화면에서 멈춘 이유와 추천 장소를 확인하세요.</span>
          <RouterLink :to="`/tasks/${proposal.taskId}`" class="btn btn-secondary btn-sm">진행 보기</RouterLink>
        </template>
        <template v-else>
          <span>거절 사유를 반영해 새 계획안을 만드는 중입니다.</span>
          <RouterLink :to="`/tasks/${proposal.taskId}`" class="btn btn-secondary btn-sm">진행 보기</RouterLink>
        </template>
      </div>

      <section v-if="priorRejections.length" class="card">
        <h2 class="card-title">반영한 거절 사유</h2>
        <p class="muted small">이 안은 앞선 안이 거절되어 다시 짠 루프 {{ proposal.loopNo }}의 안입니다. 문제로 고른 요소만 바꾸고 나머지는 최대한 유지했습니다.</p>
        <ul class="rejections">
          <li v-for="r in priorRejections" :key="r.id">
            <RouterLink :to="`/proposals/${r.id}`" class="mono">루프 {{ r.loopNo }}</RouterLink>
            <span>{{ r.plan }}</span>
            <template v-if="r.rejection">
              <strong>{{ r.rejection.title }} 거절</strong>
              <span v-if="r.rejection.issues?.length" class="badge tone-bad">{{ issueText(r.rejection.issues) }}</span>
              <span class="wrap">"{{ r.rejection.reason }}"</span>
            </template>
          </li>
        </ul>
      </section>

      <p v-if="proposal.status === 'STALE'" class="stale-note">
        승인을 기다리는 동안 촬영 데이터가 바뀌어 이 변경안은 확정할 수 없습니다.
      </p>

      <section class="card">
        <h2 class="card-title">원본 대비 변경</h2>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>항목</th>
                <th>현재 확정</th>
                <th>변경안</th>
                <th>출처</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in diffRows" :key="r.label" :class="{ changed: r.changed }">
                <td><strong>{{ r.label }}</strong></td>
                <td class="muted">{{ r.from }}</td>
                <td>
                  <strong v-if="r.changed">{{ r.to }}</strong>
                  <span v-else>{{ r.to }}</span>
                </td>
                <td>
                  <span v-if="r.source" class="badge tone-run">{{ r.source === 4 ? '4안 (대체 장소)' : `${r.source}안` }}</span>
                  <span v-else class="muted">계산값</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="proposal.explanation" class="explain">{{ proposal.explanation }}</p>
      </section>

      <section v-if="review" class="card">
        <h2 class="card-title">
          자체 검토
          <span class="small muted">승인 요청 전 Agent가 승인자 입장에서 100점 만점으로 채점, {{ review.threshold }}점 미만이면 고쳐서 다시 검토</span>
        </h2>
        <div class="total">
          <strong>{{ review.score }}</strong>
          <span class="muted">/ 100</span>
          <span class="badge" :class="review.passed ? 'tone-ok' : 'tone-stale'">
            {{ review.passed ? `${review.rounds}회차 통과` : `${review.rounds}회 도달, ${review.chosenRound}회차 안으로 요청` }}
          </span>
        </div>
        <ul class="scores">
          <li v-for="r in review.rows" :key="r.key">
            <div class="score-head">
              <span>{{ r.label }}</span>
              <strong class="mono small">{{ r.value }} / 20</strong>
            </div>
            <div class="meter"><span :style="{ width: `${(r.value / 20) * 100}%` }"></span></div>
          </li>
        </ul>
        <ol class="review-history">
          <li v-for="h in review.history" :key="h.round" :class="{ chosen: h.round === review.chosenRound }">
            <span class="mono">{{ h.round }}회차</span>
            <strong>{{ h.score }}점</strong>
            <span v-if="h.score < review.threshold" class="muted small">{{ REVIEW_ACTIONS[h.action] ?? h.action }}</span>
            <span class="small">{{ (h.feedback ?? []).join(' ') }}</span>
          </li>
        </ol>
      </section>

      <div class="grid-2">
        <section class="card">
          <h2 class="card-title">종합 점수</h2>
          <div class="total">
            <strong>{{ Number(proposal.score).toFixed(3) }}</strong>
            <span class="muted">/ 1.000</span>
          </div>
          <div class="meter mint"><span :style="{ width: `${Math.min(proposal.score, 1) * 100}%` }"></span></div>
          <ul class="scores">
            <li v-for="s in scoreRows" :key="s.key">
              <div class="score-head">
                <span>{{ s.label }}</span>
                <span class="muted small">
                  <template v-if="s.weight !== undefined">가중치 {{ Math.round(s.weight * 100) }}%, </template>
                  <strong class="mono">{{ s.value.toFixed(3) }}</strong>
                </span>
              </div>
              <div class="meter"><span :style="{ width: `${Math.min(s.value, 1) * 100}%` }"></span></div>
            </li>
          </ul>
        </section>

        <section class="card">
          <h2 class="card-title">하드 제약 체크리스트</h2>
          <ul class="checks">
            <li v-for="c in proposal.checklist" :key="c.constraint">
              <div class="row">
                <StatusBadge :status="c.status" />
                <strong>{{ CONSTRAINT_LABELS[c.constraint] ?? c.constraint }}</strong>
              </div>
              <p v-if="c.note" class="small">{{ c.note }}</p>
              <div v-if="c.evidenceIds?.length" class="row">
                <button
                  v-for="id in c.evidenceIds"
                  :key="id"
                  type="button"
                  class="chip mono"
                  @click="openEvidence(id)"
                >
                  {{ id }}
                </button>
              </div>
            </li>
          </ul>
          <div class="unresolved">
            <p class="eyebrow">미확정 항목</p>
            <ul v-if="proposal.unresolved?.length">
              <li v-for="(u, i) in proposal.unresolved" :key="i">{{ u }}</li>
            </ul>
            <p v-else class="muted small">미확정 항목이 없습니다.</p>
          </div>
        </section>
      </div>

      <section class="card">
        <h2 class="card-title">
          승인 현황
          <span class="small muted">{{ proposal.approvedCount }} / {{ proposal.requiredCount }} 완료</span>
        </h2>
        <div class="meter mint progress"><span :style="{ width: `${progress}%` }"></span></div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>역할</th>
                <th>담당 범위</th>
                <th>상태</th>
                <th>처리자</th>
                <th>시각</th>
                <th>거절 사유</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in proposal.approvals" :key="a.role" :class="{ mine: a.role === auth.user?.role }">
                <td>
                  <strong>{{ a.title }}</strong>
                  <span class="mono muted role">{{ a.role }}</span>
                </td>
                <td>{{ a.scope }}</td>
                <td><StatusBadge :status="a.status" /></td>
                <td>{{ a.userName ?? '' }}</td>
                <td class="mono">{{ dateTime(a.decidedAt) }}</td>
                <td class="wrap">
                  <span v-if="a.issues?.length" class="badge tone-bad">{{ issueText(a.issues) }}</span>
                  {{ a.reason ?? '' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="myPending" class="decide">
          <p><strong>{{ myPending.title }}</strong> 승인 차례입니다. 담당 범위: {{ myPending.scope }}</p>
          <div v-if="!rejecting" class="row">
            <button type="button" class="btn btn-primary" :disabled="deciding" @click="decide('APPROVE')">승인</button>
            <button type="button" class="btn btn-danger" :disabled="deciding" @click="rejecting = true">거절</button>
          </div>
          <div v-else class="stack">
            <div class="field">
              <span class="field-label">무엇이 문제인가요? (하나 이상)</span>
              <div class="row">
                <button
                  v-for="o in ISSUE_OPTIONS"
                  :key="o.value"
                  type="button"
                  class="chip issue"
                  :class="{ on: issues.includes(o.value) }"
                  :aria-pressed="issues.includes(o.value)"
                  @click="toggleIssue(o.value)"
                >
                  {{ o.label }}
                </button>
              </div>
            </div>
            <label class="field">
              <span class="field-label">거절 사유 (필수, {{ MIN_REASON }}자 이상, 고르지 않은 요소는 그대로 유지됩니다)</span>
              <textarea
                v-model="reason"
                class="textarea"
                placeholder="예: 성수 스튜디오는 오후 공사 소음 때문에 동시녹음이 어렵습니다."
              ></textarea>
            </label>
            <div class="row">
              <button type="button" class="btn btn-danger" :disabled="deciding || !canReject" @click="decide('REJECT')">
                거절하고 새 계획 요청
              </button>
              <button type="button" class="btn btn-secondary" :disabled="deciding" @click="rejecting = false">취소</button>
            </div>
          </div>
        </div>
      </section>

      <AskBox :proposal-id="proposal.id" />
    </template>

    <div v-else-if="!error" class="card empty">변경안을 불러오는 중입니다.</div>

    <div v-if="evidence" class="drawer-back" @click.self="evidence = null">
      <aside class="drawer" role="dialog" aria-label="근거 원문">
        <div class="drawer-head">
          <div>
            <p class="eyebrow">근거 {{ evidence.docType ?? '' }}</p>
            <h2 class="card-title">{{ evidence.title }}</h2>
            <p class="mono muted">{{ evidence.id }}<template v-if="evidence.docId"> / {{ evidence.docId }}</template></p>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" @click="evidence = null">닫기</button>
        </div>
        <p class="clause">{{ evidence.text }}</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.replan-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--card-bg);
  border: 1px solid var(--mint);
  border-radius: var(--radius-btn);
  padding: 12px 16px;
  font-weight: 600;
}

.rejections {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rejections li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.review-history {
  margin: 16px 0 0;
  padding-left: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.review-history li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  padding: 8px 10px;
  border-radius: var(--radius-btn);
  background: var(--head-bg);
}

.review-history li.chosen {
  box-shadow: inset 3px 0 0 var(--mint);
}

.chip.issue.on {
  background: var(--charcoal);
  color: var(--mint);
  border-color: var(--charcoal);
}

.stale-note {
  color: var(--stale);
  background: var(--stale-bg);
  border-radius: var(--radius-btn);
  padding: 12px 16px;
  font-weight: 600;
}

.table tr.changed td:first-child {
  box-shadow: inset 3px 0 0 var(--mint);
}

.explain {
  margin-top: 16px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.total {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 10px;
}

.total strong {
  font-size: 40px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.scores {
  list-style: none;
  margin: 20px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.score-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 14px;
}

.checks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.checks li {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.chip {
  border: 1px solid var(--line);
  background: var(--head-bg);
  border-radius: 999px;
  padding: 3px 10px;
  cursor: pointer;
}

.chip:hover {
  border-color: var(--charcoal);
}

.unresolved {
  margin-top: 16px;
}

.unresolved ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.progress {
  margin-bottom: 16px;
}

.role {
  display: block;
  font-size: 11px;
}

.table tr.mine td {
  background: #f0fbf9;
}

.decide {
  margin-top: 18px;
  padding: 16px;
  border-radius: 12px;
  border: 2px solid var(--mint);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-back {
  position: fixed;
  inset: 0;
  background: rgba(31, 41, 55, 0.28);
  z-index: 80;
  display: flex;
  justify-content: flex-end;
}

.drawer {
  width: min(440px, 100%);
  height: 100%;
  overflow-y: auto;
  background: #fff;
  padding: 24px;
  box-shadow: -12px 0 32px rgba(31, 41, 55, 0.14);
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.clause {
  white-space: pre-wrap;
  line-height: 1.75;
  background: var(--head-bg);
  border-radius: 12px;
  padding: 16px;
}
</style>
