<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import ForecastSource from '../components/ForecastSource.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { useNotificationStore } from '../stores/notifications.js'
import { useShootDayStore } from '../stores/shootDay.js'
import { addMinutes, dateTime, dateWithWeekday, ver } from '../format.js'

const notifications = useNotificationStore()
const shootDay = useShootDayStore()

const board = ref(null)
const history = ref([])
const error = ref(null)
const loading = ref(true)

const BLOCK_LABELS = { AM: '오전', PM: '오후' }

// 씬 진행과 현재 촬영지는 시계 기준이라 30초마다 다시 계산한다.
const now = ref(new Date())
let clock = null
onMounted(() => {
  clock = setInterval(() => (now.value = new Date()), 30_000)
})
onBeforeUnmount(() => clearInterval(clock))

const pad = (n) => String(n).padStart(2, '0')
const todayYmd = computed(() => `${now.value.getFullYear()}-${pad(now.value.getMonth() + 1)}-${pad(now.value.getDate())}`)
const nowMinutes = computed(() => now.value.getHours() * 60 + now.value.getMinutes())
const toMinutes = (hhmm) => {
  const [h, m] = String(hhmm).split(':').map(Number)
  return h * 60 + m
}

// 엔진과 같은 관리자 설정(시간당 촬영 불가, 경고 강수량)으로 날씨 칸 색을 정한다.
const rainRule = computed(() => board.value?.rainRule ?? { blockMm: 5, warnMm: 1 })

async function load() {
  error.value = null
  try {
    // 이력은 서버가 촬영판에 고른 촬영일 것을 읽어야 해서 촬영판을 먼저 받는다.
    const b = await api('/board/today')
    shootDay.setFromBoard(b)
    board.value = b
    history.value = (await api(`/history?shootDayId=${b.shootDay.id}`)) ?? []
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 확정과 배포, 변경 공지, 우천 알림이 오면 촬영판 내용(날씨 포함)이 바뀌었을 수 있어 다시 읽는다.
watch(
  () => notifications.lastNotification,
  (n) => {
    if (n && (n.kind === 'CALLSHEET' || n.kind === 'CHANGE_NOTICE' || n.kind === 'WEATHER')) load()
  }
)

const endTime = computed(() => {
  const ends = (board.value?.blocks ?? []).map((b) => b.end).filter(Boolean)
  return ends.sort().at(-1) ?? ''
})

// 촬영일이 오늘보다 앞이면 모두 끝난 것으로, 뒤면 아직 시작 전으로 본다.
const dayState = computed(() => {
  const date = board.value?.shootDay?.date
  if (!date) return 'future'
  if (date < todayYmd.value) return 'past'
  if (date > todayYmd.value) return 'future'
  return 'today'
})

function sceneState(start, end) {
  if (dayState.value === 'past') return 'done'
  if (dayState.value === 'future') return 'upcoming'
  if (nowMinutes.value >= toMinutes(end)) return 'done'
  if (nowMinutes.value >= toMinutes(start)) return 'current'
  return 'upcoming'
}

// 씬별 시작 시각은 API가 주지 않아서 블록 시작 시각부터 씬 길이를 차례로 더해 보여 준다.
const sceneRows = computed(() =>
  (board.value?.blocks ?? []).map((block) => {
    let cursor = block.start
    const scenes = (block.scenes ?? []).map((s) => {
      const start = cursor
      cursor = addMinutes(cursor, s.durationMin ?? 0)
      return { ...s, start, end: cursor, state: sceneState(start, cursor) }
    })
    return { block, scenes }
  })
)

const allScenes = computed(() => sceneRows.value.flatMap((g) => g.scenes))
const doneCount = computed(() => allScenes.value.filter((s) => s.state === 'done').length)
const currentScene = computed(() => allScenes.value.find((s) => s.state === 'current') ?? null)
const nextScene = computed(() => allScenes.value.find((s) => s.state === 'upcoming') ?? null)
const progressPercent = computed(() =>
  allScenes.value.length ? Math.round((doneCount.value / allScenes.value.length) * 100) : 0
)

// 지금 촬영 중인 블록, 없으면 다음 블록, 모두 끝났으면 마지막 블록의 촬영지를 현재 촬영지로 본다.
const currentBlock = computed(() => {
  const blocks = board.value?.blocks ?? []
  if (!blocks.length) return null
  if (dayState.value === 'past') return blocks.at(-1)
  if (dayState.value === 'future') return blocks[0]
  return (
    blocks.find((b) => nowMinutes.value >= toMinutes(b.start) && nowMinutes.value < toMinutes(b.end)) ??
    blocks.find((b) => nowMinutes.value < toMinutes(b.start)) ??
    blocks.at(-1)
  )
})
const currentWeather = computed(
  () => board.value?.blockWeather?.find((w) => w.blockCode === currentBlock.value?.code) ?? board.value?.weather ?? null
)
const currentHour = computed(() => (dayState.value === 'today' ? now.value.getHours() : null))

const recentHistory = computed(() => history.value.slice(0, 5))

function rainTone(mm) {
  if (mm >= rainRule.value.blockMm) return 'tone-bad'
  if (mm >= rainRule.value.warnMm) return 'tone-stale'
  return 'tone-wait'
}

// rainTone이 돌려주는 톤 이름을 shadcn Badge 변형으로 옮긴다
const TONE_VARIANT = { 'tone-bad': 'destructive', 'tone-stale': 'warning', 'tone-wait': 'secondary' }

function isInternal(link) {
  return typeof link === 'string' && link.startsWith('/')
}
</script>

<template>
  <div class="page">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="page-title">오늘의 촬영판</h1>
        <p class="mt-1 text-muted-foreground">확정된 콜시트 기준의 오늘 일정과 승인 중인 변경안입니다.</p>
      </div>
      <Badge v-if="board?.callsheet" variant="success">
        확정 콜시트 {{ ver(board.callsheet.versionNo) }}
        <template v-if="board.callsheet.createdAt">&nbsp;{{ dateTime(board.callsheet.createdAt) }}</template>
      </Badge>
    </div>

    <Alert v-if="error" variant="destructive">
      <CircleAlert />
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>
    <Card v-else-if="loading">
      <CardContent>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><Spinner /></EmptyMedia>
            <EmptyDescription>촬영판을 불러오는 중입니다.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </CardContent>
    </Card>

    <template v-if="board">
      <RouterLink
        v-if="board.pendingProposal"
        :to="`/proposals/${board.pendingProposal.id}`"
        class="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-sidebar px-5 py-4 text-sidebar-accent-foreground no-underline transition-colors hover:bg-sidebar-accent"
      >
        <strong class="min-w-0">변경안 {{ ver(board.pendingProposal.versionNo) }} 승인 진행 중</strong>
        <div class="flex flex-wrap items-center gap-3">
          <StatusBadge :status="board.pendingProposal.status" />
          <span class="text-sm text-primary underline-offset-4 hover:underline">승인 현황 보기</span>
        </div>
      </RouterLink>

      <Card
        class="grid gap-0 divide-y divide-border py-0 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_minmax(0,1fr)] min-[900px]:divide-x min-[900px]:divide-y-0"
      >
        <CardContent class="min-w-0 px-6 py-6">
          <h2 class="mb-3 text-sm font-medium">제작 연락처</h2>
          <ul class="flex flex-col gap-2.5">
            <li
              v-for="c in board.contacts"
              :key="c.title + c.name"
              class="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2.5 last:border-b-0"
            >
              <div class="flex flex-col leading-snug">
                <span>{{ c.name }}</span>
                <span class="text-sm text-muted-foreground">{{ c.title }}</span>
              </div>
              <a :href="`tel:${c.phone}`" class="mono text-sm text-foreground no-underline hover:text-primary">{{ c.phone }}</a>
            </li>
          </ul>
        </CardContent>

        <CardContent class="flex min-w-0 flex-col items-center gap-1 px-6 py-6 text-center">
          <h2 class="text-xl font-semibold tracking-tight">{{ board.project.name }}</h2>
          <p class="text-muted-foreground">{{ dateWithWeekday(board.shootDay.date) }}, {{ board.shootDay.dayNo }}회차 (총 {{ board.shootDay.totalDays }}회차)</p>
          <div class="mt-4 mb-2 flex flex-col items-center gap-1">
            <span class="text-sm text-muted-foreground">콜타임</span>
            <strong class="mono text-5xl leading-none font-bold tracking-tight min-[900px]:text-[56px]">
              {{ board.shootDay.callTime }}
            </strong>
          </div>
          <Alert v-if="board.shootDay.notice" class="border-transparent bg-muted text-left">
            <AlertTitle>공지</AlertTitle>
            <AlertDescription class="text-foreground">{{ board.shootDay.notice }}</AlertDescription>
          </Alert>
        </CardContent>

        <CardContent class="min-w-0 px-6 py-6">
          <h2 class="mb-1 text-sm font-medium">
            날씨 <span class="text-muted-foreground">현재 촬영지 {{ currentWeather?.locationName }}</span>
            <span v-if="currentWeather?.indoor" class="text-muted-foreground">(실내)</span>
          </h2>
          <p class="text-xs text-muted-foreground">시간당 강수량(mm), 촬영 불가 기준 {{ rainRule.blockMm }}mm</p>
          <ForecastSource :forecast="currentWeather?.forecast" />
          <p v-if="currentWeather?.summary" class="mt-1 text-sm text-muted-foreground">{{ currentWeather.summary }}</p>
          <div class="mt-2.5 grid grid-cols-[repeat(auto-fill,minmax(54px,1fr))] gap-1.5">
            <Badge
              v-for="h in currentWeather?.hourly ?? []"
              :key="h.hour"
              :variant="TONE_VARIANT[rainTone(h.precipMm)]"
              :class="['h-auto w-full flex-col gap-0 rounded-md py-1', h.hour === currentHour && 'ring-2 ring-primary']"
            >
              <span class="font-normal">{{ h.hour }}시</span>
              <span>{{ h.precipMm }}mm</span>
            </Badge>
          </div>

          <h3 class="mt-6 text-sm font-medium">팀별 콜타임</h3>
          <Table class="mt-1">
            <TableBody>
              <TableRow v-for="c in board.crewCallTimes" :key="c.team" class="hover:bg-transparent">
                <TableCell class="px-0 py-1.5">{{ c.team }}</TableCell>
                <TableCell class="mono px-0 py-1.5 text-right">{{ c.time }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <div class="mt-3 flex items-baseline justify-between">
            <span class="text-sm text-muted-foreground">종료 예정</span>
            <strong class="mono text-2xl font-semibold">{{ endTime }}</strong>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>촬영지</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead class="text-muted-foreground">블록</TableHead>
                <TableHead class="text-muted-foreground">촬영지</TableHead>
                <TableHead class="text-muted-foreground">주소</TableHead>
                <TableHead class="text-muted-foreground">시간대</TableHead>
                <TableHead class="text-muted-foreground">비고</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="b in board.blocks" :key="b.code">
                <TableCell>{{ BLOCK_LABELS[b.code] ?? b.code }}</TableCell>
                <TableCell class="font-medium">{{ b.location?.name }}</TableCell>
                <TableCell>{{ b.location?.address ?? b.location?.region }}</TableCell>
                <TableCell class="mono">{{ b.start }}~{{ b.end }}</TableCell>
                <TableCell class="min-w-45 whitespace-normal">
                  {{ b.location?.indoor ? '실내' : '야외' }}<span v-if="b.equipment?.length" class="text-muted-foreground">, 장비 {{ b.equipment.map((e) => (e.available === false ? `${e.name}(사용 불가)` : e.name)).join(', ') }}</span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>씬 스케줄</CardTitle>
          <CardAction class="flex items-center gap-3">
            <span class="text-sm text-muted-foreground">오늘 씬 진행</span>
            <strong class="mono text-lg">{{ doneCount }}/{{ allScenes.length }}</strong>
          </CardAction>
        </CardHeader>
        <CardContent class="flex flex-col gap-2 pb-0">
          <Progress :model-value="progressPercent" aria-label="오늘 씬 진행률" />
          <p class="text-sm text-muted-foreground">
            <template v-if="dayState === 'future'">촬영일 전입니다. 첫 씬은 {{ nextScene?.start }} {{ nextScene?.code }}입니다.</template>
            <template v-else-if="dayState === 'past' || !nextScene && !currentScene">오늘 촬영할 씬을 모두 마쳤습니다.</template>
            <template v-else-if="currentScene">지금 {{ currentScene.code }} {{ currentScene.title }} 촬영 중 ({{ currentScene.start }}~{{ currentScene.end }})</template>
            <template v-else>다음 씬은 {{ nextScene?.start }} {{ nextScene?.code }} {{ nextScene?.title }}입니다.</template>
          </p>
        </CardContent>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead class="text-muted-foreground">시간</TableHead>
                <TableHead class="text-muted-foreground">씬</TableHead>
                <TableHead class="text-muted-foreground">제목</TableHead>
                <TableHead class="text-muted-foreground">배우</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-for="g in sceneRows" :key="g.block.code">
                <TableRow class="bg-muted/50 hover:bg-muted/50">
                  <TableCell colspan="4" class="text-xs text-muted-foreground">
                    {{ BLOCK_LABELS[g.block.code] ?? g.block.code }} 블록, {{ g.block.location?.name }}, {{ g.block.start }}~{{ g.block.end }}
                  </TableCell>
                </TableRow>
                <TableRow
                  v-for="s in g.scenes"
                  :key="s.code"
                  :aria-current="s.state === 'current' ? 'true' : undefined"
                  :class="[
                    s.state === 'current' && 'bg-yellow-200 font-semibold text-yellow-950 shadow-[inset_6px_0_0_var(--color-amber-500)] hover:bg-yellow-200 dark:bg-yellow-400/25 dark:text-yellow-50 dark:hover:bg-yellow-400/25',
                    s.state === 'done' && 'text-muted-foreground'
                  ]"
                >
                  <TableCell class="mono">{{ s.start }}~{{ s.end }}</TableCell>
                  <TableCell class="font-medium">
                    {{ s.code }}
                    <Badge v-if="s.state === 'current'" class="ml-1.5 gap-1.5 border-amber-600 bg-amber-400 text-yellow-950">
                      <span class="size-1.5 animate-pulse rounded-full bg-red-600" aria-hidden="true" />촬영 중
                    </Badge>
                    <Badge v-else-if="s.state === 'done'" variant="secondary" class="ml-1.5">완료</Badge>
                  </TableCell>
                  <TableCell>{{ s.title }}</TableCell>
                  <TableCell>{{ (s.actors ?? []).join(', ') }}</TableCell>
                </TableRow>
              </template>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>최근 변동 이력</CardTitle>
          <CardAction>
            <Button variant="link" size="sm" as-child>
              <RouterLink to="/history">이력 전체 보기</RouterLink>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <ul v-if="recentHistory.length" class="flex flex-col gap-2.5">
            <li v-for="(h, i) in recentHistory" :key="i" class="flex flex-wrap gap-x-3.5 gap-y-1">
              <span class="mono text-muted-foreground">{{ dateTime(h.at) }}</span>
              <RouterLink
                v-if="isInternal(h.link)"
                :to="h.link"
                class="text-foreground underline underline-offset-4 hover:text-primary"
              >
                {{ h.text }}
              </RouterLink>
              <span v-else>{{ h.text }}</span>
            </li>
          </ul>
          <Empty v-else class="p-4">
            <EmptyHeader>
              <EmptyDescription>아직 변동 이력이 없습니다.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
