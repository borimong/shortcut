<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CircleAlert, Info } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '../api.js'
import { useShootDayStore } from '../stores/shootDay.js'
import { useToastStore } from '../stores/toast.js'
import { EVENT_TYPES } from '../labels.js'

const router = useRouter()
const toast = useToastStore()
const shootDay = useShootDayStore()

const type = ref('RAIN')
const detail = ref('')
const instruction = ref('')
const busy = ref(false)
const error = ref(null)

// 문장(상세 내용)은 Agent가 읽고, 아래 구조화된 값은 backend가 촬영 데이터에 바로 반영해 엔진이 판정에 쓴다.
const options = ref(null)
const rain = ref({ locationId: null, fromHour: 13, toHour: 17, mm: 8 })
const actor = ref({ actorId: null, mode: 'ABSENT', from: '09:00', to: '15:00' })
const cancelLocationId = ref(null)
const brokenEquipment = ref([])
const disaster = ref({ region: '', alertKind: '호우 경보', from: '13:00', to: '17:00' })

const current = computed(() => EVENT_TYPES.find((t) => t.value === type.value))
const HOURS = Array.from({ length: 18 }, (_, i) => i + 6)
const selectClass =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50'

onMounted(async () => {
  try {
    const o = await api(`/events/options?shootDayId=${await shootDay.ensure()}`)
    options.value = o
    rain.value.locationId = o.pmLocationId
    cancelLocationId.value = o.pmLocationId
    actor.value.actorId = o.actors[0]?.id ?? null
    disaster.value.region = o.locations.find((l) => l.id === o.pmLocationId)?.region ?? o.regions[0] ?? ''
  } catch (e) {
    error.value = e
  }
})

const nameOf = (list, id) => (options.value?.[list] ?? []).find((x) => x.id === id)?.name ?? ''

// 화면에서 고른 값을 backend가 받는 변경 목록으로 바꾼다. 기타는 구조화된 변경이 없다.
const changes = computed(() => {
  if (!options.value) return []
  switch (type.value) {
    case 'RAIN':
      return rain.value.locationId && rain.value.mm !== '' && rain.value.mm !== null
        ? [{ kind: 'RAIN_FORECAST', targetId: rain.value.locationId, fromHour: rain.value.fromHour, toHour: rain.value.toHour, mm: Number(rain.value.mm) }]
        : []
    case 'ACTOR_SCHEDULE':
      if (!actor.value.actorId) return []
      return actor.value.mode === 'ABSENT'
        ? [{ kind: 'ACTOR_ABSENT', targetId: actor.value.actorId }]
        : [{ kind: 'ACTOR_WINDOW', targetId: actor.value.actorId, from: actor.value.from, to: actor.value.to }]
    case 'LOCATION_CANCEL':
      return cancelLocationId.value ? [{ kind: 'LOCATION_UNAVAILABLE', targetId: cancelLocationId.value }] : []
    case 'EQUIPMENT_FAILURE':
      return brokenEquipment.value.map((id) => ({ kind: 'EQUIPMENT_UNAVAILABLE', targetId: id }))
    case 'DISASTER':
      return disaster.value.region && disaster.value.alertKind
        ? [{ kind: 'DISASTER_ALERT', region: disaster.value.region, alertKind: disaster.value.alertKind, from: disaster.value.from, to: disaster.value.to }]
        : []
    default:
      return []
  }
})

const summary = computed(() =>
  changes.value.map((c) => {
    switch (c.kind) {
      case 'RAIN_FORECAST':
        return `${nameOf('locations', c.targetId)} ${c.fromHour}~${c.toHour}시 시간당 ${c.mm}mm 비`
      case 'ACTOR_ABSENT':
        return `${nameOf('actors', c.targetId)} 오늘 촬영 불참`
      case 'ACTOR_WINDOW':
        return `${nameOf('actors', c.targetId)} 가용 시간 ${c.from}~${c.to}`
      case 'LOCATION_UNAVAILABLE':
        return `${nameOf('locations', c.targetId)} 사용 불가`
      case 'EQUIPMENT_UNAVAILABLE':
        return `${nameOf('equipment', c.targetId)} 사용 불가`
      case 'DISASTER_ALERT':
        return `${c.region} ${c.alertKind} ${c.from}~${c.to}`
      default:
        return ''
    }
  })
)

// 유형을 바꾸면 이전 유형에서 고른 장비 같은 값이 남지 않게 비운다.
watch(type, () => {
  brokenEquipment.value = []
  error.value = null
})

const canSubmit = computed(() => !busy.value && (detail.value.trim() || summary.value.length))

async function submit() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = null
  try {
    // 상세 내용을 비워 두면 고른 변경 요약을 그대로 상세 내용으로 쓴다.
    const text = detail.value.trim() || `${current.value.label}: ${summary.value.join(', ')}`
    const body = { shootDayId: shootDay.id, type: type.value, detail: text, changes: changes.value }
    if (instruction.value.trim()) body.instruction = instruction.value.trim()
    const res = await api('/events', { method: 'POST', body })
    if (res.duplicate) toast.info('같은 변경이 이미 접수되어 있어 기존 진행 화면으로 이동합니다.')
    router.push(`/tasks/${res.taskId}`)
  } catch (e) {
    error.value = e
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page mx-auto w-full max-w-[760px]">
    <div class="flex flex-col gap-1">
      <h1 class="page-title">변경 입력</h1>
      <p class="text-muted-foreground">현장에서 생긴 변경을 입력하면 Agent가 오후 블록을 다시 짜고 승인 요청을 올립니다.</p>
    </div>

    <form @submit.prevent="submit">
      <Card>
        <CardContent>
          <FieldGroup>
            <FieldSet>
              <FieldLegend variant="label">변경 유형</FieldLegend>
              <!-- 단일 선택에서 선택 해제는 막는다 -->
              <ToggleGroup
                type="single"
                variant="outline"
                :spacing="2"
                :model-value="type"
                aria-label="변경 유형"
                class="grid w-full grid-cols-3 sm:grid-cols-6"
                @update:model-value="(v) => v && (type = v)"
              >
                <ToggleGroupItem
                  v-for="t in EVENT_TYPES"
                  :key="t.value"
                  :value="t.value"
                  class="h-11 w-full data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
                >
                  {{ t.label }}
                </ToggleGroupItem>
              </ToggleGroup>
            </FieldSet>

            <FieldSet v-if="options && type !== 'OTHER'" class="rounded-lg border border-dashed p-4">
              <FieldLegend variant="label">촬영 데이터에 반영할 변경</FieldLegend>
              <FieldDescription>고른 값은 엔진이 바로 판정에 씁니다. 예를 들어 장비를 고장으로 고르면 그 장비가 든 안은 후보에서 빠집니다.</FieldDescription>

              <div v-if="type === 'RAIN'" class="grid gap-3 sm:grid-cols-4">
                <Field class="sm:col-span-2">
                  <FieldLabel for="rain-location">장소</FieldLabel>
                  <select id="rain-location" v-model="rain.locationId" :class="selectClass">
                    <option v-for="l in options.locations" :key="l.id" :value="l.id">{{ l.name }} ({{ l.indoor ? '실내' : '야외' }})</option>
                  </select>
                </Field>
                <Field>
                  <FieldLabel for="rain-from">시작</FieldLabel>
                  <select id="rain-from" v-model="rain.fromHour" :class="selectClass">
                    <option v-for="h in HOURS" :key="h" :value="h">{{ h }}시</option>
                  </select>
                </Field>
                <Field>
                  <FieldLabel for="rain-to">끝</FieldLabel>
                  <select id="rain-to" v-model="rain.toHour" :class="selectClass">
                    <option v-for="h in HOURS" :key="h" :value="h" :disabled="h < rain.fromHour">{{ h }}시</option>
                  </select>
                </Field>
                <Field class="sm:col-span-2">
                  <FieldLabel for="rain-mm">시간당 강수량 (mm)</FieldLabel>
                  <Input id="rain-mm" v-model="rain.mm" type="number" min="0" max="300" step="0.5" />
                </Field>
              </div>

              <div v-else-if="type === 'ACTOR_SCHEDULE'" class="grid gap-3 sm:grid-cols-4">
                <Field class="sm:col-span-2">
                  <FieldLabel for="actor">배우</FieldLabel>
                  <select id="actor" v-model="actor.actorId" :class="selectClass">
                    <option v-for="a in options.actors" :key="a.id" :value="a.id">{{ a.name }} (현재 {{ a.availableFrom }}~{{ a.availableTo }})</option>
                  </select>
                </Field>
                <Field class="sm:col-span-2">
                  <FieldLabel for="actor-mode">변경</FieldLabel>
                  <select id="actor-mode" v-model="actor.mode" :class="selectClass">
                    <option value="ABSENT">오늘 불참</option>
                    <option value="WINDOW">가용 시간 변경</option>
                  </select>
                </Field>
                <template v-if="actor.mode === 'WINDOW'">
                  <Field class="sm:col-span-2">
                    <FieldLabel for="actor-from">가용 시작</FieldLabel>
                    <Input id="actor-from" v-model="actor.from" type="time" />
                  </Field>
                  <Field class="sm:col-span-2">
                    <FieldLabel for="actor-to">가용 끝</FieldLabel>
                    <Input id="actor-to" v-model="actor.to" type="time" />
                  </Field>
                </template>
              </div>

              <Field v-else-if="type === 'LOCATION_CANCEL'">
                <FieldLabel for="cancel-location">취소된 장소</FieldLabel>
                <select id="cancel-location" v-model="cancelLocationId" :class="selectClass">
                  <option v-for="l in options.locations" :key="l.id" :value="l.id" :disabled="!l.available">
                    {{ l.name }}{{ l.available ? '' : ' (이미 사용 불가)' }}
                  </option>
                </select>
              </Field>

              <div v-else-if="type === 'EQUIPMENT_FAILURE'" class="grid gap-2 sm:grid-cols-2">
                <label
                  v-for="e in options.equipment"
                  :key="e.id"
                  :class="['flex items-center gap-2 rounded-md border px-3 py-2 text-sm', !e.available && 'text-muted-foreground']"
                >
                  <input v-model="brokenEquipment" type="checkbox" :value="e.id" :disabled="!e.available" class="size-4 accent-primary" />
                  {{ e.name }}<span v-if="!e.available">(이미 사용 불가)</span>
                </label>
              </div>

              <div v-else-if="type === 'DISASTER'" class="grid gap-3 sm:grid-cols-4">
                <Field class="sm:col-span-2">
                  <FieldLabel for="disaster-region">지역</FieldLabel>
                  <select id="disaster-region" v-model="disaster.region" :class="selectClass">
                    <option v-for="r in options.regions" :key="r" :value="r">{{ r }}</option>
                  </select>
                </Field>
                <Field class="sm:col-span-2">
                  <FieldLabel for="disaster-kind">재난 문자 종류</FieldLabel>
                  <Input id="disaster-kind" v-model="disaster.alertKind" placeholder="예) 호우 경보, 강풍 주의보, 지진" />
                </Field>
                <Field class="sm:col-span-2">
                  <FieldLabel for="disaster-from">시작</FieldLabel>
                  <Input id="disaster-from" v-model="disaster.from" type="time" />
                </Field>
                <Field class="sm:col-span-2">
                  <FieldLabel for="disaster-to">끝</FieldLabel>
                  <Input id="disaster-to" v-model="disaster.to" type="time" />
                </Field>
              </div>

              <Alert v-if="summary.length" class="border-transparent bg-muted">
                <Info />
                <AlertDescription class="text-foreground">반영할 변경: {{ summary.join(', ') }}</AlertDescription>
              </Alert>
            </FieldSet>

            <Field>
              <FieldLabel for="change-detail">상세 내용</FieldLabel>
              <Textarea id="change-detail" v-model="detail" class="min-h-28" :placeholder="current?.hint" />
              <FieldDescription>언제, 어디서, 무엇이, 얼마나 바뀌었는지와 누구에게서 연락받았는지 적으면 Agent가 더 정확히 판단합니다. 비워 두면 위에서 고른 변경 요약을 씁니다.</FieldDescription>
            </Field>

            <Field>
              <FieldLabel for="change-instruction">감독 지시 (선택)</FieldLabel>
              <Input id="change-instruction" v-model="instruction" placeholder="예) 추가 비용이 들어도 실내 스튜디오로, 오후 촬영은 17시 전에 끝내기" />
            </Field>

            <Alert v-if="error" variant="destructive">
              <CircleAlert />
              <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
            </Alert>
          </FieldGroup>
        </CardContent>
        <CardFooter class="flex-wrap justify-end gap-2">
          <Button as-child variant="outline" class="flex-1 sm:flex-none">
            <RouterLink to="/board">취소</RouterLink>
          </Button>
          <Button type="submit" class="flex-1 sm:flex-none" :disabled="!canSubmit">
            <Spinner v-if="busy" data-icon="inline-start" />
            {{ busy ? '접수 중' : '변경 접수하고 재계획 시작' }}
          </Button>
        </CardFooter>
      </Card>
    </form>
  </div>
</template>
