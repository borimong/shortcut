<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
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
              <span class="mono text-sm">{{ c.phoneMasked }}</span>
            </li>
          </ul>
        </CardContent>

        <CardContent class="flex min-w-0 flex-col items-center gap-1 px-6 py-6 text-center">
          <h2 class="text-xl font-semibold tracking-tight">{{ board.project.name }}</h2>
          <p class="text-muted-foreground">{{ dateWithWeekday(board.shootDay.date) }}, 1회차 (총 1회차)</p>
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
          <h2 class="mb-1 text-sm font-medium">{{ board.weather?.locationName }} 강수확률</h2>
          <p v-if="board.weather?.summary" class="text-sm text-muted-foreground">{{ board.weather.summary }}</p>
          <div class="mt-2.5 grid grid-cols-[repeat(auto-fill,minmax(54px,1fr))] gap-1.5">
            <Badge
              v-for="h in board.weather?.hourly ?? []"
              :key="h.hour"
              :variant="TONE_VARIANT[rainTone(h.precipProb)]"
              class="h-auto w-full flex-col gap-0 rounded-md py-1"
            >
              <span class="font-normal">{{ h.hour }}시</span>
              <span>{{ h.precipProb }}%</span>
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
                  {{ b.location?.indoor ? '실내' : '야외' }}<span v-if="b.equipment?.length" class="text-muted-foreground">, 장비 {{ b.equipment.map((e) => e.name).join(', ') }}</span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>씬 스케줄</CardTitle>
        </CardHeader>
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
                <TableRow v-for="s in g.scenes" :key="s.code">
                  <TableCell class="mono">{{ s.start }}~{{ s.end }}</TableCell>
                  <TableCell class="font-medium">{{ s.code }}</TableCell>
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
