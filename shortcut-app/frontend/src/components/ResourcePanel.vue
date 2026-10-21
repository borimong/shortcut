<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyMedia } from '@/components/ui/empty'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useResourceStore } from '../stores/resources.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime, dateWithWeekday } from '../format.js'
import { RESOURCE_OPTIONS, RESOURCE_STATUS } from '../labels.js'

const open = defineModel('open', { type: Boolean, default: false })
const store = useResourceStore()
const toast = useToastStore()
const router = useRouter()

const GROUPS = [
  { key: 'equipment', label: '장비' },
  { key: 'locations', label: '장소' },
  { key: 'actors', label: '배우' }
]
const PRESSED =
  'flex-1 aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

const tab = ref('all')
const editing = ref(null)
const form = reactive({ status: 'OK', scope: 'day', untilDate: '', memo: '', from: '', to: '' })
// 저장 전에 모아 둔 변경이다. 키는 "종류:id", 값은 고친 상태와 원래 항목이다.
const staged = ref({})
const replan = ref(false)
const replanTouched = ref(false)
const saving = ref(false)

watch(open, (value) => {
  if (value) store.load()
  else editing.value = null
})

const board = computed(() => store.board)
const groups = computed(() =>
  GROUPS.filter((g) => tab.value === 'all' || tab.value === g.key).map((g) => ({ ...g, items: board.value?.[g.key] ?? [] }))
)
const stagedList = computed(() => Object.values(staged.value))
const okCount = computed(() => store.all.length - store.unavailableCount - store.limitedCount)

const key = (group, item) => `${group}:${item.id}`
const hhmm = (t) => (t ? String(t).slice(0, 5) : '')

function shownStatus(group, item) {
  return staged.value[key(group, item)]?.status ?? item.status
}

function detail(group, item) {
  const parts = []
  if (group === 'actors' && item.status !== 'ABSENT') parts.push(`${hhmm(item.availableFrom)}~${hhmm(item.availableTo)}`)
  if (item.usage) parts.push(item.usage)
  if (item.override?.untilDate) parts.push(`${item.override.untilDate.slice(5).replace('-', '.')}까지`)
  if (item.override?.fromOtherDay) parts.push('다른 촬영일에 등록')
  return parts.join(', ')
}

function overrideNote(o) {
  const who = o.createdBy ? `, ${o.createdBy}` : ''
  const event = o.eventId ? `, 변경 #${o.eventId}` : ''
  return `${dateTime(o.createdAt)} 기록${who}${event}${o.memo ? `. 메모: ${o.memo}` : ''}`
}

function begin(group, item) {
  if (!board.value?.canEdit) return
  const k = key(group, item)
  if (editing.value === k) {
    editing.value = null
    return
  }
  const s = staged.value[k]
  form.status = s?.status ?? item.status
  form.untilDate = s ? s.untilDate : (item.override?.untilDate ?? '')
  form.scope = form.untilDate ? 'until' : 'day'
  form.memo = s ? s.memo : (item.override?.memo ?? '')
  form.from = s?.from ?? hhmm(item.availableFrom)
  form.to = s?.to ?? hhmm(item.availableTo)
  editing.value = k
}

const formError = computed(() => {
  if (form.status === 'LIMITED' && !(form.from && form.to && form.from < form.to)) {
    return '가용 시작 시각은 끝 시각보다 빨라야 합니다.'
  }
  if (form.status !== 'OK' && form.scope === 'until' && !(form.untilDate && form.untilDate >= board.value?.shootDate)) {
    return '끝 날짜를 이 촬영일 이후로 고르세요.'
  }
  return ''
})

function stage(group, item) {
  const k = key(group, item)
  const entry = {
    group,
    item,
    status: form.status,
    untilDate: form.status !== 'OK' && form.scope === 'until' ? form.untilDate : '',
    memo: form.status === 'OK' ? '' : form.memo.trim(),
    from: form.from,
    to: form.to
  }
  const same =
    entry.status === item.status &&
    entry.untilDate === (item.override?.untilDate ?? '') &&
    entry.memo === (item.override?.memo ?? '') &&
    (entry.status !== 'LIMITED' || (entry.from === hhmm(item.availableFrom) && entry.to === hhmm(item.availableTo)))
  const next = { ...staged.value }
  if (same) delete next[k]
  else next[k] = entry
  staged.value = next
  // 오늘 일정에서 쓰는 자원을 바꿨을 때만 재계획을 기본으로 켠다. 사용자가 직접 고르면 그 선택을 따른다.
  if (!replanTouched.value) replan.value = Object.values(next).some((e) => e.item.usage)
  editing.value = null
}

function discard(group, item) {
  const next = { ...staged.value }
  delete next[key(group, item)]
  staged.value = next
}

function toRequest() {
  const changes = []
  const clears = []
  for (const e of stagedList.value) {
    const { group, item } = e
    if (e.status === 'OK') {
      if (item.override) clears.push(item.override.id)
      continue
    }
    const base = { targetId: item.id, memo: e.memo || null }
    if (group === 'equipment') {
      changes.push({ ...base, kind: 'EQUIPMENT_UNAVAILABLE', status: e.status, untilDate: e.untilDate || null })
    } else if (group === 'locations') {
      changes.push({ ...base, kind: 'LOCATION_UNAVAILABLE', untilDate: e.untilDate || null })
    } else if (e.status === 'ABSENT') {
      changes.push({ ...base, kind: 'ACTOR_ABSENT' })
    } else {
      changes.push({ ...base, kind: 'ACTOR_WINDOW', from: e.from, to: e.to })
    }
  }
  return { changes, clears }
}

async function save() {
  if (saving.value || !stagedList.value.length) return
  saving.value = true
  try {
    const result = await store.save({ ...toRequest(), replan: replan.value })
    staged.value = {}
    replanTouched.value = false
    replan.value = false
    toast.info(
      result.superseded
        ? `저장했습니다. 승인을 기다리던 변경안 ${result.superseded}건은 무효가 되었습니다.`
        : '저장했습니다.'
    )
    if (result.taskId) {
      open.value = false
      router.push(`/tasks/${result.taskId}`)
    }
  } catch (e) {
    toast.error(e)
    // 그사이 다른 사람이 바꿨으면 모아 둔 변경은 옛 상태 기준이라 버리고 새로 불러온다.
    if (e.code === 'DATA_VERSION_CONFLICT') {
      staged.value = {}
      store.load()
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Sheet v-model:open="open">
    <!-- 시트 기본값(오른쪽은 3/4 폭)보다 우선하도록 같은 data-side 조건으로 덮는다. 휴대폰에서는 전체 폭으로 연다 -->
    <SheetContent side="right" class="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[460px]">
      <SheetHeader class="gap-1 border-b px-6 pt-5 pb-4">
        <SheetTitle class="text-lg">자원 현황</SheetTitle>
        <SheetDescription>
          <template v-if="board">{{ dateWithWeekday(board.shootDate) }} 촬영일, 데이터 버전 {{ board.dataVersion }}</template>
          <template v-else>장비, 장소, 배우 상태를 불러오는 중입니다.</template>
        </SheetDescription>
        <div v-if="board" class="mt-2 flex flex-wrap gap-2">
          <Badge variant="destructive">사용 불가 {{ store.unavailableCount }}</Badge>
          <Badge variant="warning">시간 제한 {{ store.limitedCount }}</Badge>
          <Badge variant="success">정상 {{ okCount }}</Badge>
        </div>
      </SheetHeader>

      <div v-if="board" class="flex min-h-0 flex-1 flex-col">
        <div class="px-6 pt-4">
          <Tabs v-model="tab">
            <TabsList class="w-full">
              <TabsTrigger value="all">전체</TabsTrigger>
              <TabsTrigger v-for="g in GROUPS" :key="g.key" :value="g.key">{{ g.label }}</TabsTrigger>
            </TabsList>
          </Tabs>
          <p v-if="!board.canEdit" class="mt-3 text-sm text-muted-foreground">상태 변경은 제작 PD와 연출감독만 할 수 있습니다.</p>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pt-2 pb-6">
          <section v-for="g in groups" :key="g.key" class="mt-3">
            <h3 class="mb-1 text-xs font-medium text-muted-foreground">{{ g.label }}</h3>
            <ul class="flex flex-col">
              <li v-for="item in g.items" :key="item.id" class="border-b last:border-b-0">
                <button
                  type="button"
                  class="flex w-full items-center gap-3 rounded-md py-2.5 text-left text-sm hover:bg-muted/60 disabled:cursor-default disabled:hover:bg-transparent"
                  :disabled="!board.canEdit"
                  :aria-expanded="editing === key(g.key, item)"
                  @click="begin(g.key, item)"
                >
                  <span class="min-w-0 flex-1">
                    <span class="block truncate font-medium">{{ item.name }}</span>
                    <span v-if="detail(g.key, item)" class="block truncate text-xs text-muted-foreground">{{ detail(g.key, item) }}</span>
                  </span>
                  <Badge v-if="staged[key(g.key, item)]" variant="outline">저장 전</Badge>
                  <Badge :variant="RESOURCE_STATUS[shownStatus(g.key, item)][1]">{{ RESOURCE_STATUS[shownStatus(g.key, item)][0] }}</Badge>
                </button>

                <div v-if="editing === key(g.key, item)" class="mb-3 rounded-lg border border-primary/40 bg-accent/30 p-3">
                  <FieldGroup class="gap-4">
                    <FieldSet>
                      <FieldLegend variant="label">상태</FieldLegend>
                      <ToggleGroup
                        v-model="form.status"
                        type="single"
                        variant="outline"
                        size="sm"
                        class="w-full"
                        @update:model-value="(v) => { if (!v) form.status = item.status }"
                      >
                        <ToggleGroupItem v-for="s in RESOURCE_OPTIONS[g.key]" :key="s" :value="s" :class="PRESSED">
                          {{ RESOURCE_STATUS[s][0] }}
                        </ToggleGroupItem>
                      </ToggleGroup>
                    </FieldSet>

                    <div v-if="g.key === 'actors' && form.status === 'LIMITED'" class="grid grid-cols-2 gap-3">
                      <Field>
                        <FieldLabel :for="`from-${item.id}`">가용 시작</FieldLabel>
                        <Input :id="`from-${item.id}`" v-model="form.from" type="time" />
                      </Field>
                      <Field>
                        <FieldLabel :for="`to-${item.id}`">가용 끝</FieldLabel>
                        <Input :id="`to-${item.id}`" v-model="form.to" type="time" />
                      </Field>
                    </div>

                    <FieldSet v-if="g.key !== 'actors' && form.status !== 'OK'">
                      <FieldLegend variant="label">적용 기간</FieldLegend>
                      <RadioGroup v-model="form.scope" class="gap-2.5">
                        <div class="flex items-center gap-2">
                          <RadioGroupItem :id="`day-${item.id}`" value="day" />
                          <Label :for="`day-${item.id}`">이번 촬영일만</Label>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                          <RadioGroupItem :id="`until-${item.id}`" value="until" />
                          <Label :for="`until-${item.id}`">날짜까지 모든 촬영일</Label>
                          <Input
                            v-model="form.untilDate"
                            type="date"
                            :min="board.shootDate"
                            class="h-8 w-40"
                            aria-label="적용 끝 날짜"
                            :disabled="form.scope !== 'until'"
                          />
                        </div>
                      </RadioGroup>
                    </FieldSet>

                    <Field v-if="form.status !== 'OK'">
                      <FieldLabel :for="`memo-${item.id}`">메모</FieldLabel>
                      <Input :id="`memo-${item.id}`" v-model="form.memo" maxlength="200" placeholder="예: 배터리 불량, 대여사 교체 요청" />
                    </Field>

                    <p v-if="item.override" class="text-xs text-muted-foreground">{{ overrideNote(item.override) }}</p>
                    <p v-if="formError" class="text-xs text-destructive">{{ formError }}</p>

                    <div class="flex flex-wrap justify-end gap-2">
                      <Button v-if="staged[key(g.key, item)]" type="button" variant="ghost" size="sm" @click="discard(g.key, item); editing = null">
                        변경 취소
                      </Button>
                      <Button type="button" variant="outline" size="sm" @click="editing = null">닫기</Button>
                      <Button type="button" size="sm" :disabled="!!formError" @click="stage(g.key, item)">적용</Button>
                    </div>
                  </FieldGroup>
                </div>
              </li>
            </ul>
          </section>
        </div>

        <SheetFooter v-if="board.canEdit" class="flex-row flex-wrap items-center gap-3 border-t px-6 py-3.5">
          <div class="flex flex-1 items-center gap-2">
            <Checkbox id="resource-replan" v-model="replan" @update:model-value="replanTouched = true" />
            <Label for="resource-replan" class="text-sm font-normal">저장하면 재계획 요청</Label>
          </div>
          <Button type="button" :disabled="saving || !stagedList.length" @click="save">
            <Spinner v-if="saving" data-icon="inline-start" />
            {{ stagedList.length ? `변경 ${stagedList.length}건 저장` : '바꾼 항목 없음' }}
          </Button>
        </SheetFooter>
      </div>

      <Empty v-else class="flex-1">
        <EmptyMedia><Spinner v-if="store.loading" /></EmptyMedia>
        <EmptyDescription>{{ store.error ? store.error.message : '불러오는 중입니다.' }}</EmptyDescription>
      </Empty>
    </SheetContent>
  </Sheet>
</template>
