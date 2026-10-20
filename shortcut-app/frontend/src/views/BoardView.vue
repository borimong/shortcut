<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { useNotificationStore } from '../stores/notifications.js'
import { addMinutes, dateTime, dateWithWeekday, ver } from '../format.js'
import { SHOOT_DAY_ID } from '../labels.js'

const notifications = useNotificationStore()

const board = ref(null)
const history = ref([])
const error = ref(null)
const loading = ref(true)

const BLOCK_LABELS = { AM: '오전', PM: '오후' }
// 엔진의 우천 하드 제약(70 이상)과 경고(30 이상) 기준을 화면 강조에도 똑같이 쓴다.
const RAIN_HARD = 70
const RAIN_SOFT = 30

async function load() {
  error.value = null
  try {
    const [b, h] = await Promise.all([api('/board/today'), api(`/history?shootDayId=${SHOOT_DAY_ID}`)])
    board.value = b
    history.value = h ?? []
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 확정과 배포, 변경 공지가 오면 촬영판 내용이 바뀌었을 수 있어 다시 읽는다.
watch(
  () => notifications.lastNotification,
  (n) => {
    if (n && (n.kind === 'CALLSHEET' || n.kind === 'CHANGE_NOTICE')) load()
  }
)

const endTime = computed(() => {
  const ends = (board.value?.blocks ?? []).map((b) => b.end).filter(Boolean)
  return ends.sort().at(-1) ?? ''
})

// 씬별 시작 시각은 API가 주지 않아서 블록 시작 시각부터 씬 길이를 차례로 더해 보여 준다.
const sceneRows = computed(() =>
  (board.value?.blocks ?? []).map((block) => {
    let cursor = block.start
    const scenes = (block.scenes ?? []).map((s) => {
      const start = cursor
      cursor = addMinutes(cursor, s.durationMin ?? 0)
      return { ...s, start, end: cursor }
    })
    return { block, scenes }
  })
)

const recentHistory = computed(() => history.value.slice(0, 5))

function rainTone(p) {
  if (p >= RAIN_HARD) return 'tone-bad'
  if (p >= RAIN_SOFT) return 'tone-stale'
  return 'tone-wait'
}

function isInternal(link) {
  return typeof link === 'string' && link.startsWith('/')
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">오늘의 촬영판</h1>
        <p class="page-sub">확정된 콜시트와 진행 중인 변경안을 한눈에 봅니다.</p>
      </div>
      <span v-if="board?.callsheet" class="badge tone-ok">
        확정 콜시트 {{ ver(board.callsheet.versionNo) }}
        <template v-if="board.callsheet.createdAt">&nbsp;{{ dateTime(board.callsheet.createdAt) }}</template>
      </span>
    </div>

    <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>
    <div v-else-if="loading" class="card empty">촬영판을 불러오는 중입니다.</div>

    <template v-if="board">
      <RouterLink v-if="board.pendingProposal" :to="`/proposals/${board.pendingProposal.id}`" class="banner">
        <div>
          <p class="eyebrow">진행 중인 변경안</p>
          <strong>변경안 {{ ver(board.pendingProposal.versionNo) }} 승인 진행 중</strong>
        </div>
        <div class="row">
          <StatusBadge :status="board.pendingProposal.status" />
          <span class="banner-go">승인 현황 보기</span>
        </div>
      </RouterLink>

      <section class="card sheet">
        <div class="col left">
          <p class="eyebrow">Production</p>
          <h2 class="col-title">제작 연락처</h2>
          <ul class="contacts">
            <li v-for="c in board.contacts" :key="c.title + c.name">
              <div>
                <strong>{{ c.name }}</strong>
                <span class="muted small">{{ c.title }}</span>
              </div>
              <span class="mono">{{ c.phoneMasked }}</span>
            </li>
          </ul>
        </div>

        <div class="col center">
          <p class="eyebrow">Call Sheet</p>
          <h2 class="title">{{ board.project.name }}</h2>
          <p class="day">Day 1 of 1</p>
          <p class="date">{{ dateWithWeekday(board.shootDay.date) }}</p>
          <div class="start">
            <span class="eyebrow">Start time</span>
            <strong>{{ board.shootDay.callTime }}</strong>
          </div>
          <div v-if="board.shootDay.notice" class="notice">
            <span class="eyebrow">Notice</span>
            <p>{{ board.shootDay.notice }}</p>
          </div>
        </div>

        <div class="col right">
          <p class="eyebrow">Weather</p>
          <h2 class="col-title">{{ board.weather?.locationName }} 강수확률</h2>
          <p v-if="board.weather?.summary" class="muted small">{{ board.weather.summary }}</p>
          <div class="hours">
            <span v-for="h in board.weather?.hourly ?? []" :key="h.hour" class="hour" :class="rainTone(h.precipProb)">
              <span>{{ h.hour }}시</span>
              <strong>{{ h.precipProb }}%</strong>
            </span>
          </div>

          <p class="eyebrow crew-head">Crew Call time</p>
          <table class="crew">
            <tbody>
              <tr v-for="c in board.crewCallTimes" :key="c.team">
                <td>{{ c.team }}</td>
                <td class="mono">{{ c.time }}</td>
              </tr>
            </tbody>
          </table>
          <div class="end">
            <span class="eyebrow">End Time</span>
            <strong>{{ endTime }}</strong>
          </div>
        </div>
      </section>

      <section class="card">
        <h2 class="card-title">Location</h2>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>블록</th>
                <th>촬영지</th>
                <th>주소</th>
                <th>시간대</th>
                <th>비고</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in board.blocks" :key="b.code">
                <td>{{ BLOCK_LABELS[b.code] ?? b.code }}</td>
                <td><strong>{{ b.location?.name }}</strong></td>
                <td>{{ b.location?.address ?? b.location?.region }}</td>
                <td class="mono">{{ b.start }}~{{ b.end }}</td>
                <td class="wrap">
                  {{ b.location?.indoor ? '실내' : '야외' }}<span v-if="b.equipment?.length" class="muted">, 장비 {{ b.equipment.map((e) => e.name).join(', ') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2 class="card-title">씬 스케줄</h2>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>시간</th>
                <th>씬</th>
                <th>제목</th>
                <th>배우</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="g in sceneRows" :key="g.block.code">
                <tr class="group-row">
                  <td colspan="4">
                    {{ BLOCK_LABELS[g.block.code] ?? g.block.code }} 블록, {{ g.block.location?.name }}, {{ g.block.start }}~{{ g.block.end }}
                  </td>
                </tr>
                <tr v-for="s in g.scenes" :key="s.code">
                  <td class="mono">{{ s.start }}~{{ s.end }}</td>
                  <td><strong>{{ s.code }}</strong></td>
                  <td>{{ s.title }}</td>
                  <td>{{ (s.actors ?? []).join(', ') }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2 class="card-title">
          최근 변동 이력
          <RouterLink to="/history" class="link small">전체 보기</RouterLink>
        </h2>
        <ul v-if="recentHistory.length" class="history">
          <li v-for="(h, i) in recentHistory" :key="i">
            <span class="mono muted">{{ dateTime(h.at) }}</span>
            <RouterLink v-if="isInternal(h.link)" :to="h.link" class="link">{{ h.text }}</RouterLink>
            <span v-else>{{ h.text }}</span>
          </li>
        </ul>
        <p v-else class="empty">아직 변동 이력이 없습니다.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px 24px;
  border-radius: var(--radius-card);
  background: var(--charcoal);
  color: #fff;
  text-decoration: none;
  box-shadow: var(--shadow);
}

.banner .eyebrow {
  color: var(--mint);
}

.banner-go {
  color: var(--mint);
  font-weight: 700;
}

.sheet {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 1fr);
  padding: 0;
}

.col {
  padding: 28px 24px;
  min-width: 0;
}

.col + .col {
  border-left: 1px solid var(--line);
}

.col-title {
  font-size: 16px;
  font-weight: 700;
  margin: 2px 0 12px;
}

.contacts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.contacts li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--line);
}

.contacts li div {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.center {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-top: 4px;
}

.day {
  color: var(--text-sub);
  font-weight: 600;
}

.date {
  font-weight: 700;
}

.start {
  margin: 18px 0 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.start strong {
  font-size: 56px;
  line-height: 1.05;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.notice {
  width: 100%;
  background: var(--head-bg);
  border-radius: 12px;
  padding: 12px 14px;
  text-align: left;
}

.hours {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(54px, 1fr));
  gap: 6px;
  margin-top: 10px;
}

.hour {
  display: flex;
  flex-direction: column;
  align-items: center;
  border-radius: 8px;
  padding: 4px 0;
  font-size: 12px;
}

.crew-head {
  margin-top: 20px;
}

.crew {
  width: 100%;
  border-collapse: collapse;
  margin-top: 6px;
  font-size: 14px;
}

.crew td {
  padding: 6px 0;
  border-bottom: 1px solid var(--line);
}

.crew td:last-child {
  text-align: right;
}

.end {
  margin-top: 14px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.end strong {
  font-size: 22px;
}

.history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history li {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}

@media (max-width: 900px) {
  .sheet {
    grid-template-columns: minmax(0, 1fr);
  }

  .col + .col {
    border-left: 0;
    border-top: 1px solid var(--line);
  }

  .start strong {
    font-size: 48px;
  }
}
</style>
