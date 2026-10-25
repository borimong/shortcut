<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { CircleAlert, MapPin, Printer } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '../api.js'
import { useNotificationStore } from '../stores/notifications.js'
import { useShootDayStore } from '../stores/shootDay.js'
import { addMinutes, dateTime, dateWithWeekday, ver, won } from '../format.js'

const notifications = useNotificationStore()
const shootDay = useShootDayStore()

const board = ref(null)
const versions = ref([])
const sheet = ref(null)
const selectedVersion = ref('')
const error = ref(null)
const loading = ref(true)
// 확정 뒤 실행팀이 잡은 예약, 렌탈, 허가, 차량, 연락, 장부 현황이다. 조회가 안 되면 숨긴다.
const ops = ref(null)

const BLOCK_LABELS = { AM: '오전', PM: '오후' }
// 일출, 일몰 데이터가 없어서 씬 시작 시각으로 낮과 밤을 나눈다
const DAY_START_HOUR = 6
const NIGHT_START_HOUR = 18

async function loadSheet(shootDayId, versionNo) {
  sheet.value = versionNo ? await api(`/callsheets/${shootDayId}/${versionNo}`) : null
}

async function load() {
  error.value = null
  try {
    const b = await api('/board/today')
    shootDay.setFromBoard(b)
    const list = await api(`/callsheets?shootDayId=${b.shootDay.id}`)
    board.value = b
    versions.value = [...(list ?? [])].sort((x, y) => y.versionNo - x.versionNo)
    const keep = versions.value.some((v) => String(v.versionNo) === selectedVersion.value)
    if (!keep) selectedVersion.value = String(b.callsheet?.versionNo ?? versions.value[0]?.versionNo ?? '')
    await loadSheet(b.shootDay.id, selectedVersion.value)
    ops.value = await api(`/shoot-days/${b.shootDay.id}/ops`).catch(() => null)
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

onMounted(load)

watch(selectedVersion, async (v, old) => {
  if (!old || !board.value || v === old) return
  try {
    await loadSheet(board.value.shootDay.id, v)
  } catch (e) {
    error.value = e
  }
})

// 확정이나 변경 공지가 오면 최신 콜시트로 다시 읽는다
watch(
  () => notifications.lastNotification,
  (n) => {
    if (n && (n.kind === 'CALLSHEET' || n.kind === 'CHANGE_NOTICE')) {
      selectedVersion.value = ''
      load()
    }
  }
)

const OPS_STATUS = {
  HELD: '가예약',
  CONFIRMED: '확정',
  CANCELLED: '취소',
  MANUAL_PENDING: '처리 대기',
  BOOKED: '예약',
  QUOTED: '견적',
  APPROVED: '허가',
  DENIED: '반려',
  APPLIED: '신청'
}
const opsStatus = (s) => OPS_STATUS[s] ?? s
const activeOnly = (list) => (list ?? []).filter((x) => x.status !== 'CANCELLED')
const questionCount = (m) => (Array.isArray(m?.questions) ? m.questions.length : (m?.questions ?? 0))
const opsLines = computed(() => {
  const o = ops.value
  if (!o) return []
  const lines = []
  const res = activeOnly(o.reservations)
  if (res.length)
    lines.push({
      label: '장소 예약',
      text: res.map((r) => `${r.locationName ?? ''} ${r.reservationId ?? r.id} ${opsStatus(r.status)}`.trim()).join(', ')
    })
  const rentals = activeOnly(o.rentals)
  if (rentals.length)
    lines.push({
      label: '장비 렌탈',
      text: rentals.map((r) => `${r.bookingId ?? r.id} ${opsStatus(r.status)}${r.deliveryAt ? `, ${r.deliveryAt} 도착` : ''}`).join(', ')
    })
  const permits = o.permits ?? []
  if (permits.length)
    lines.push({
      label: '촬영 허가',
      text: permits.map((p) => `${p.kind === 'DRONE' ? '드론' : '장소'} ${p.permitId ?? p.id} ${opsStatus(p.status)}`).join(', ')
    })
  const trips = activeOnly(o.transports)
  if (trips.length)
    lines.push({
      label: '이동 수단',
      text: trips.map((t) => `${t.departAt ?? ''} ${t.pickup ?? ''} 출발 (${t.bookingId ?? t.id})`.trim()).join(', ')
    })
  if (o.messages?.sent)
    lines.push({ label: '연락', text: `발송 ${o.messages.sent}건, 확인 ${o.messages.acked ?? 0}건, 질문 ${questionCount(o.messages)}건` })
  if (o.budget?.capKrw !== undefined && (o.budget.spentKrw ?? 0) > 0)
    lines.push({
      label: '제작비',
      text: `집행 ${won(o.budget.spentKrw)}, 잔액 ${won(o.budget.remainingKrw)}${o.budget.over ? ' (예산 초과)' : ''}`,
      warn: o.budget.over
    })
  return lines
})

const isLatest = computed(() => String(board.value?.callsheet?.versionNo ?? '') === selectedVersion.value)
const sheetMeta = computed(() => versions.value.find((v) => String(v.versionNo) === selectedVersion.value))
const blocks = computed(() => sheet.value?.blocks ?? board.value?.blocks ?? [])
const shootDate = computed(() => sheet.value?.shootDate ?? board.value?.shootDay.date)
const callTime = computed(() => sheet.value?.callTime ?? board.value?.shootDay.callTime)
const firstShot = computed(() => blocks.value.map((b) => b.start).filter(Boolean).sort()[0] ?? '')
const wrapTime = computed(() => blocks.value.map((b) => b.end).filter(Boolean).sort().at(-1) ?? '')

const staffContacts = computed(() =>
  (board.value?.contacts ?? [])
    .filter((c) => c.title !== '매니저')
    .map((c) => ({ ...c, title: c.title.replace(/\s*\(.*\)$/, '') }))
)

function dayPart(hhmm) {
  const h = Number(hhmm.split(':')[0])
  return h >= DAY_START_HOUR && h < NIGHT_START_HOUR ? '낮' : '밤'
}

// 씬별 시작 시각은 블록 시작부터 씬 길이를 차례로 더해 만든다 (촬영판과 같은 방식)
const scheduleRows = computed(() => {
  const rows = []
  blocks.value.forEach((block, i) => {
    const prev = blocks.value[i - 1]
    if (prev?.end && block.start && prev.end < block.start) {
      const [ph, pm] = prev.end.split(':').map(Number)
      const [bh, bm] = block.start.split(':').map(Number)
      const gap = bh * 60 + bm - (ph * 60 + pm)
      const moving = prev.location?.id !== block.location?.id
      rows.push({
        kind: 'gap',
        key: `gap-${block.code}`,
        text: `${moving ? `장소 이동 (${prev.location?.name}에서 ${block.location?.name}으로)` : '블록 사이 대기'}, ${prev.end}~${block.start}, ${gap}분`
      })
    }
    rows.push({
      kind: 'block',
      key: `block-${block.code}`,
      text: `${BLOCK_LABELS[block.code] ?? block.code} 블록, ${block.location?.name}, ${block.start}~${block.end}`
    })
    let cursor = block.start
    for (const s of block.scenes ?? []) {
      const start = cursor
      cursor = addMinutes(cursor, s.durationMin ?? 0)
      rows.push({
        kind: 'scene',
        key: s.code,
        ...s,
        start,
        end: cursor,
        indoor: Boolean(block.location?.indoor),
        dayPart: dayPart(start),
        location: block.location?.name
      })
    }
  })
  return rows
})

const scenes = computed(() => scheduleRows.value.filter((r) => r.kind === 'scene'))
const totalMinutes = computed(() => scenes.value.reduce((sum, s) => sum + (s.durationMin ?? 0), 0))

const cast = computed(() => {
  const byName = new Map()
  for (const s of scenes.value) {
    for (const name of s.actors ?? []) {
      if (!byName.has(name)) byName.set(name, { name, scenes: [], first: s, last: s })
      const a = byName.get(name)
      a.scenes.push(s.code)
      a.last = s
    }
  }
  const managers = new Map(
    (board.value?.contacts ?? []).filter((c) => c.title === '매니저').map((c) => [c.name, c.phone])
  )
  return [...byName.values()]
    .sort((a, b) => a.first.start.localeCompare(b.first.start) || a.name.localeCompare(b.name, 'ko'))
    .map((a) => ({ ...a, manager: managers.get(`${a.name} 매니저`) ?? '' }))
})

const crewCalls = computed(() =>
  [...(Array.isArray(board.value?.crewCallTimes) ? board.value.crewCallTimes : [])].sort((a, b) =>
    String(a.time).localeCompare(String(b.time))
  )
)

const weather = computed(() => board.value?.weather ?? null)
const maxPrecip = computed(() => Math.max(0, ...(weather.value?.hourly ?? []).map((h) => h.precipMm)))
const rainRule = computed(() => board.value?.rainRule ?? { blockMm: 5, warnMm: 1 })

function rainVariant(mm) {
  if (mm >= rainRule.value.blockMm) return 'destructive'
  if (mm >= rainRule.value.warnMm) return 'warning'
  return 'secondary'
}

function mapUrl(address) {
  return `https://map.naver.com/p/search/${encodeURIComponent(address)}`
}

function print() {
  window.print()
}
</script>

<template>
  <div class="page callsheet">
    <div class="flex flex-wrap items-end justify-between gap-3 print:hidden">
      <div>
        <h1 class="page-title">콜시트</h1>
        <p class="mt-1 text-muted-foreground">확정된 콜시트를 현장 배포용 한 장으로 정리했습니다.</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <!-- 버전 목록이 늦게 와도 인쇄 버튼이 밀리지 않도록 선택 상자를 처음부터 둔다 -->
        <Select v-model="selectedVersion" :disabled="versions.length < 2">
          <SelectTrigger class="w-40" aria-label="콜시트 버전">
            <SelectValue placeholder="버전 선택" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="v in versions" :key="v.versionNo" :value="String(v.versionNo)">
              {{ ver(v.versionNo) }}{{ String(v.versionNo) === String(board?.callsheet?.versionNo) ? ' (최신)' : '' }}
            </SelectItem>
          </SelectContent>
        </Select>
        <Button :disabled="!board" @click="print">
          <Printer />
          인쇄
        </Button>
      </div>
    </div>

    <Alert v-if="error" variant="destructive">
      <CircleAlert />
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>
    <!-- 촬영판을 받은 뒤에는 콜시트 카드가 바로 그려지므로, 로딩 카드가 함께 있다가 사라지며 카드를 밀어 올리지 않게 한다 -->
    <Card v-else-if="loading && !board">
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon"><Spinner /></EmptyMedia>
          <EmptyDescription>콜시트를 불러오는 중입니다.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </Card>

    <template v-if="board">
      <RouterLink
        v-if="board.pendingProposal && isLatest"
        :to="`/proposals/${board.pendingProposal.id}`"
        class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted px-4 py-3 text-sm text-foreground no-underline hover:bg-accent print:hidden"
      >
        <span>변경안 {{ ver(board.pendingProposal.versionNo) }}이 승인 중입니다. 확정되면 콜시트가 새 버전으로 바뀝니다.</span>
        <span class="text-primary">승인 현황 보기</span>
      </RouterLink>

      <Card class="sheet gap-0 py-0">
        <!-- 상단: 연락처 / 작품과 콜타임 / 날씨 -->
        <header
          class="grid divide-y divide-border md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)_minmax(0,1fr)] md:divide-x md:divide-y-0 print:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)_minmax(0,1fr)] print:divide-x print:divide-y-0"
        >
          <section class="min-w-0 p-5 print:p-3">
            <h2 class="sheet-label">제작 연락처</h2>
            <ul class="mt-2 flex flex-col">
              <li
                v-for="c in staffContacts"
                :key="c.title + c.name"
                class="flex items-baseline justify-between gap-3 border-b border-border py-1.5 last:border-b-0"
              >
                <span class="min-w-0">
                  <span class="text-xs text-muted-foreground">{{ c.title }}</span>
                  <span class="block text-sm font-medium">{{ c.name }}</span>
                </span>
                <span class="mono shrink-0 text-sm">{{ c.phone }}</span>
              </li>
            </ul>
          </section>

          <section class="flex min-w-0 flex-col items-center p-5 text-center print:p-3">
            <Badge variant="outline">확정 콜시트 {{ ver(selectedVersion) }}</Badge>
            <p class="mt-3 text-xl font-bold tracking-tight">{{ board.project.name }}</p>
            <p class="text-sm text-muted-foreground">촬영일 {{ dateWithWeekday(shootDate) }}</p>
            <p class="sheet-label mt-4">전체 콜타임</p>
            <p class="mono text-5xl leading-none font-bold tracking-tight md:text-6xl print:text-5xl">{{ callTime }}</p>
            <dl class="mt-4 grid w-full grid-cols-2 gap-2 text-sm">
              <div class="rounded-md bg-muted px-3 py-2">
                <dt class="text-xs text-muted-foreground">첫 촬영</dt>
                <dd class="mono font-semibold">{{ firstShot }}</dd>
              </div>
              <div class="rounded-md bg-muted px-3 py-2">
                <dt class="text-xs text-muted-foreground">종료 예정</dt>
                <dd class="mono font-semibold">{{ wrapTime }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="weather" class="min-w-0 p-5 print:p-3">
            <h2 class="sheet-label">날씨</h2>
            <p class="mt-2 text-sm font-medium">{{ weather.locationName }} 기준, 최대 시간당 강수량 {{ maxPrecip }}mm</p>
            <p v-if="weather.summary" class="text-sm text-muted-foreground">{{ weather.summary }}</p>
            <div class="mt-3 grid grid-cols-[repeat(auto-fill,minmax(48px,1fr))] gap-1">
              <Badge
                v-for="h in weather.hourly ?? []"
                :key="h.hour"
                :variant="rainVariant(h.precipMm)"
                class="h-auto w-full flex-col gap-0 rounded-md py-1"
              >
                <span class="font-normal">{{ h.hour }}시</span>
                <span>{{ h.precipMm }}mm</span>
              </Badge>
            </div>
          </section>
        </header>

        <template v-if="board.shootDay.notice">
          <Separator />
          <section class="sheet-section">
            <h2 class="sheet-label">공지</h2>
            <p class="mt-1 font-medium">{{ board.shootDay.notice }}</p>
          </section>
        </template>

        <template v-if="opsLines.length">
          <Separator />
          <section class="sheet-section">
            <h2 class="sheet-label">실행 현황</h2>
            <dl class="mt-2 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
              <template v-for="l in opsLines" :key="l.label">
                <dt class="text-muted-foreground">{{ l.label }}</dt>
                <dd class="break-words" :class="{ 'text-destructive': l.warn }">{{ l.text }}</dd>
              </template>
            </dl>
          </section>
        </template>

        <Separator />
        <section class="sheet-section">
          <h2 class="sheet-label">촬영지</h2>
          <ol class="mt-3 grid gap-3 md:grid-cols-2 print:grid-cols-2">
            <li
              v-for="(b, i) in blocks"
              :key="b.code"
              class="flex min-w-0 gap-3 rounded-lg border border-border p-3"
            >
              <span
                class="mono flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold"
              >{{ i + 1 }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <strong>{{ b.location?.name }}</strong>
                  <Badge :variant="b.location?.indoor ? 'secondary' : 'info'">{{ b.location?.indoor ? '실내' : '야외' }}</Badge>
                </div>
                <p class="text-sm text-muted-foreground">{{ b.location?.address ?? b.location?.region }}</p>
                <p class="mt-1 text-sm">
                  <span class="mono">{{ b.start }}~{{ b.end }}</span>, {{ BLOCK_LABELS[b.code] ?? b.code }} 블록
                </p>
                <p v-if="b.equipment?.length" class="text-sm text-muted-foreground">
                  장비: {{ b.equipment.map((e) => e.name).join(', ') }}
                </p>
                <a
                  v-if="b.location?.address"
                  :href="mapUrl(b.location.address)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="mt-1 inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline print:hidden"
                >
                  <MapPin class="size-3.5" />지도에서 보기
                </a>
              </div>
            </li>
          </ol>
        </section>

        <Separator />
        <section class="sheet-section">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <h2 class="sheet-label">씬 스케줄</h2>
            <span class="text-xs text-muted-foreground">총 {{ scenes.length }}씬, {{ totalMinutes }}분</span>
          </div>
          <Table class="mt-2 min-w-[760px] print:min-w-0">
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead class="text-muted-foreground">시간</TableHead>
                <TableHead class="text-muted-foreground">씬</TableHead>
                <TableHead class="text-muted-foreground">실내/야외</TableHead>
                <TableHead class="text-muted-foreground">낮/밤</TableHead>
                <TableHead class="text-muted-foreground">장면 설명</TableHead>
                <TableHead class="text-muted-foreground">출연</TableHead>
                <TableHead class="text-right text-muted-foreground">분량</TableHead>
                <TableHead class="text-muted-foreground">장소</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-for="r in scheduleRows" :key="r.key">
                <TableRow v-if="r.kind === 'block'" class="bg-muted hover:bg-muted">
                  <TableCell colspan="8" class="text-xs font-medium">{{ r.text }}</TableCell>
                </TableRow>
                <TableRow v-else-if="r.kind === 'gap'" class="hover:bg-transparent">
                  <TableCell colspan="8" class="text-xs text-muted-foreground">{{ r.text }}</TableCell>
                </TableRow>
                <TableRow v-else>
                  <TableCell class="mono">{{ r.start }}~{{ r.end }}</TableCell>
                  <TableCell class="mono font-semibold">{{ r.code }}</TableCell>
                  <TableCell>
                    <Badge :variant="r.indoor ? 'secondary' : 'info'">{{ r.indoor ? '실내' : '야외' }}</Badge>
                  </TableCell>
                  <TableCell>{{ r.dayPart }}</TableCell>
                  <TableCell class="font-medium">{{ r.title }}</TableCell>
                  <TableCell>{{ (r.actors ?? []).join(', ') }}</TableCell>
                  <TableCell class="mono text-right">{{ r.durationMin }}분</TableCell>
                  <TableCell>{{ r.location }}</TableCell>
                </TableRow>
              </template>
            </TableBody>
          </Table>
        </section>

        <template v-if="cast.length">
          <Separator />
          <section class="sheet-section">
            <h2 class="sheet-label">출연진</h2>
            <Table class="mt-2 min-w-[640px] print:min-w-0">
              <TableHeader>
                <TableRow class="hover:bg-transparent">
                  <TableHead class="text-muted-foreground">번호</TableHead>
                  <TableHead class="text-muted-foreground">배우</TableHead>
                  <TableHead class="text-muted-foreground">출연 씬</TableHead>
                  <TableHead class="text-muted-foreground">첫 촬영</TableHead>
                  <TableHead class="text-muted-foreground">촬영 종료</TableHead>
                  <TableHead class="text-muted-foreground">첫 촬영지</TableHead>
                  <TableHead class="text-muted-foreground">매니저 연락처</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="(a, i) in cast" :key="a.name">
                  <TableCell class="mono text-muted-foreground">{{ i + 1 }}</TableCell>
                  <TableCell class="font-medium">{{ a.name }}</TableCell>
                  <TableCell class="mono">{{ a.scenes.join(', ') }}</TableCell>
                  <TableCell class="mono font-semibold">{{ a.first.start }}</TableCell>
                  <TableCell class="mono">{{ a.last.end }}</TableCell>
                  <TableCell>{{ a.first.location }}</TableCell>
                  <TableCell class="mono">{{ a.manager }}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </section>
        </template>

        <template v-if="crewCalls.length">
          <Separator />
          <section class="sheet-section">
            <h2 class="sheet-label">부서별 콜타임</h2>
            <ul class="mt-3 grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-2">
              <li
                v-for="c in crewCalls"
                :key="c.team"
                class="flex items-baseline justify-between gap-2 rounded-lg border border-border px-3 py-2"
              >
                <span class="min-w-0 text-sm whitespace-nowrap">{{ c.team }}</span>
                <span class="mono shrink-0 font-semibold">{{ c.time }}</span>
              </li>
            </ul>
          </section>
        </template>

        <Separator />
        <footer class="flex flex-wrap justify-between gap-2 px-5 py-3 text-xs text-muted-foreground print:px-3">
          <span>{{ board.project.name }}, 콜시트 {{ ver(selectedVersion) }}</span>
          <span v-if="sheetMeta?.createdAt">확정 {{ dateTime(sheetMeta.createdAt) }}</span>
        </footer>
      </Card>
    </template>
  </div>
</template>

<style scoped>
.sheet-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--muted-foreground);
}
.sheet-section {
  padding: 20px;
}
</style>

<style>
/* 콜시트 화면에서만 A4 한 장 배포용으로 인쇄한다 */
@media print {
  @page {
    size: A4;
    margin: 10mm;
  }
  /* Tailwind 크기가 rem 기준이라 루트 글자 크기를 줄여 한 장에 담는다 */
  html:has(.callsheet) {
    font-size: 12px;
  }
  body:has(.callsheet) {
    font-size: 9.5pt;
    line-height: 1.45;
    background: #fff;
  }
  body:has(.callsheet) main.wrap {
    max-width: none;
    padding: 0;
  }
  .callsheet {
    padding: 0;
    gap: 0;
  }
  .callsheet * {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  .callsheet .sheet {
    border-radius: 0;
    overflow: visible;
  }
  .callsheet .sheet-section {
    padding: 10px 12px;
    break-inside: avoid;
  }
  .callsheet [data-slot='table-container'] {
    overflow: visible;
  }
  .callsheet [data-slot='table'] {
    font-size: 10px;
  }
  .callsheet [data-slot='table-cell'],
  .callsheet [data-slot='table-head'] {
    height: auto;
    padding: 3px 6px;
  }
  .callsheet tr {
    break-inside: avoid;
  }
}
</style>
