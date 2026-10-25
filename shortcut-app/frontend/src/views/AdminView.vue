<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '../api.js'
import { useAuthStore } from '../stores/auth.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime } from '../format.js'

const auth = useAuthStore()
const toast = useToastStore()

const error = ref(null)
const settings = ref(null)
const rules = ref(null)
const roleOptions = ref([])
const members = ref([])
const saving = ref({ settings: false, rules: false, rain: false, weather: false })
const confirmWithdraw = ref(null)

// 변경안에서 무엇이 바뀌었을 때 그 역할의 승인을 받을지다. 항상은 모든 변경안에 적용된다.
const CHANGE_KINDS = [
  { value: 'ALWAYS', label: '항상', hint: '모든 변경안' },
  { value: 'LOCATION', label: '장소 변경', hint: '촬영지가 바뀔 때' },
  { value: 'EQUIPMENT', label: '장비 변경', hint: '장비 구성이 바뀔 때' },
  { value: 'TIME', label: '시간 변경', hint: '촬영 시간대가 바뀔 때' },
  { value: 'SCENE', label: '씬 순서 변경', hint: '블록 안 씬 순서가 바뀔 때' },
  { value: 'COST', label: '추가 비용', hint: '비용이 늘어날 때' }
]

async function load() {
  error.value = null
  try {
    const [s, r, m] = await Promise.all([api('/admin/settings'), api('/admin/approver-rules'), api('/admin/members')])
    settings.value = { ...s }
    rules.value = Object.fromEntries(CHANGE_KINDS.map((k) => [k.value, [...(r.rules[k.value] ?? [])]]))
    roleOptions.value = r.roles
    members.value = m
  } catch (e) {
    error.value = e
  }
}

onMounted(load)

async function saveSettings() {
  saving.value.settings = true
  try {
    const body = {
      maxLoops: Number(settings.value.maxLoops),
      rainBlockMm: Number(settings.value.rainBlockMm),
      rainWarnMm: Number(settings.value.rainWarnMm),
      rainAlertLeadHours: Number(settings.value.rainAlertLeadHours),
      weatherSource: settings.value.weatherSource,
      mockVenueConflict: !!settings.value.mockVenueConflict,
      mockPermitDenied: !!settings.value.mockPermitDenied
    }
    settings.value = { ...(await api('/admin/settings', { method: 'PUT', body })) }
    toast.info('운영 설정을 저장했습니다. 다음 안건부터 적용됩니다.')
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value.settings = false
  }
}

async function checkRain() {
  saving.value.rain = true
  try {
    const res = await api('/admin/rain-alerts/check', { method: 'POST' })
    toast.info(res.sent ? `우천 알림 ${res.sent}건을 보냈습니다: ${res.alerts.join(', ')}` : '지금 보낼 우천 알림이 없습니다.')
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value.rain = false
  }
}

async function refreshWeather() {
  saving.value.weather = true
  try {
    const res = await api('/admin/weather/refresh', { method: 'POST' })
    const failed = res.failed.length ? ` 받지 못한 곳(마지막 예보 사용): ${res.failed.join(', ')}` : ''
    const bumped = res.dataVersionBumped ? ` 비 예보가 기준을 넘나들어 촬영일 ${res.dataVersionBumped}곳의 대기 변경안을 무효로 돌렸습니다.` : ''
    toast.info(`날씨 예보를 갱신했습니다(촬영일별 장소 ${res.updated}건).${failed}${bumped}`)
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value.weather = false
  }
}

function toggleRule(kind, role) {
  const list = rules.value[kind]
  const i = list.indexOf(role)
  if (i >= 0) list.splice(i, 1)
  else list.push(role)
}

async function saveRules() {
  saving.value.rules = true
  try {
    const res = await api('/admin/approver-rules', { method: 'PUT', body: { rules: rules.value } })
    rules.value = Object.fromEntries(CHANGE_KINDS.map((k) => [k.value, [...(res.rules[k.value] ?? [])]]))
    toast.info('최종 승인자 규칙을 저장했습니다. 새로 만드는 변경안부터 적용됩니다.')
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value.rules = false
  }
}

async function setAdmin(m, admin) {
  try {
    const updated = await api(`/admin/members/${m.id}/admin`, { method: 'PUT', body: { admin } })
    members.value = members.value.map((x) => (x.id === m.id ? updated : x))
  } catch (e) {
    toast.error(e)
  }
}

async function withdraw(m) {
  try {
    const updated = await api(`/admin/members/${m.id}`, { method: 'DELETE' })
    members.value = members.value.map((x) => (x.id === m.id ? updated : x))
    toast.info(`${m.name} 님을 탈퇴 처리했습니다.`)
  } catch (e) {
    toast.error(e)
  } finally {
    confirmWithdraw.value = null
  }
}

const isMe = (m) => m.username === auth.user?.username
const activeMembers = computed(() => members.value.filter((m) => m.active))
const leftMembers = computed(() => members.value.filter((m) => !m.active))
</script>

<template>
  <div class="page">
    <div class="flex flex-col gap-1">
      <h1 class="page-title">관리자</h1>
      <p class="text-muted-foreground">재계획 한도, 우천 기준과 알림, 최종 승인자, 구성원을 관리합니다.</p>
    </div>

    <Alert v-if="error" variant="destructive">
      <CircleAlert />
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>

    <Card v-if="settings">
      <CardHeader>
        <CardTitle>운영 설정</CardTitle>
        <CardDescription>
          마지막 변경 {{ settings.updatedAt ? dateTime(settings.updatedAt) : '없음' }}<template v-if="settings.updatedBy">, {{ settings.updatedBy }}</template>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="saveSettings">
          <FieldGroup class="grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel for="max-loops">안건당 최대 재계획 횟수</FieldLabel>
              <Input id="max-loops" v-model="settings.maxLoops" type="number" min="1" max="10" required />
              <FieldDescription>거절되면 다시 계획하는 횟수의 상한입니다. 넘으면 사람에게 넘깁니다(1~10회).</FieldDescription>
            </Field>
            <Field>
              <FieldLabel for="rain-block">촬영 불가 강수량 (시간당 mm)</FieldLabel>
              <Input id="rain-block" v-model="settings.rainBlockMm" type="number" min="0.1" max="100" step="0.5" required />
              <FieldDescription>이 이상 비가 오는 야외 촬영안은 엔진이 막고, 우천 알림도 이 기준으로 보냅니다.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel for="rain-warn">우천 대비 경고 강수량 (시간당 mm)</FieldLabel>
              <Input id="rain-warn" v-model="settings.rainWarnMm" type="number" min="0" max="100" step="0.5" required />
              <FieldDescription>이 이상이면 후보로 남기되 우비, 방수 준비를 미확정 항목으로 표시합니다.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel for="rain-lead">우천 알림 시점 (몇 시간 전)</FieldLabel>
              <Input id="rain-lead" v-model="settings.rainAlertLeadHours" type="number" min="0" max="48" required />
              <FieldDescription>비가 시작되는 촬영 시각보다 이만큼 먼저 전 스태프에게 "비로 촬영 불가" 알림을 보냅니다.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel for="weather-source">날씨 예보</FieldLabel>
              <Select v-model="settings.weatherSource">
                <SelectTrigger id="weather-source" class="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="LIVE">실시간 예보 (Open-Meteo, 1시간마다 갱신)</SelectItem>
                  <SelectItem value="SEED">시연용 고정 예보 (1회차 한강 공원 13시부터 8mm)</SelectItem>
                </SelectContent>
              </Select>
              <FieldDescription>실시간 예보는 장소 위경도로 받습니다. 시연 날 비가 오지 않으면 고정 예보로 바꿉니다. 변경 입력으로 넣은 강수량은 어느 쪽이든 예보보다 우선합니다.</FieldDescription>
            </Field>
          </FieldGroup>
          <!-- 가상 외부 서비스가 일부러 실패하게 만들어 실행팀의 뒤 단계 중단, 재지시, 사람 보고를 시연한다 -->
          <FieldGroup class="mt-6 gap-3">
            <h3 class="text-sm font-medium">실행팀 실패 시연</h3>
            <Field orientation="horizontal">
              <Checkbox id="mock-venue" v-model="settings.mockVenueConflict" />
              <div class="flex flex-col gap-0.5">
                <FieldLabel for="mock-venue">장소 가예약 실패 시연</FieldLabel>
                <FieldDescription>켜면 가상 아워플레이스가 같은 시간대 예약이 있다며 가예약을 거절합니다. 2, 3단계가 실행되지 않는지 볼 수 있습니다.</FieldDescription>
              </div>
            </Field>
            <Field orientation="horizontal">
              <Checkbox id="mock-permit" v-model="settings.mockPermitDenied" />
              <div class="flex flex-col gap-0.5">
                <FieldLabel for="mock-permit">촬영 허가 반려 시연</FieldLabel>
                <FieldDescription>켜면 가상 허가 기관이 촬영 허가를 반려합니다. 연락과 장부 전에 멈추는지 볼 수 있습니다.</FieldDescription>
              </div>
            </Field>
          </FieldGroup>
          <div class="mt-4 flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" :disabled="saving.weather" @click="refreshWeather">
              <Spinner v-if="saving.weather" data-icon="inline-start" />지금 예보 갱신
            </Button>
            <Button type="button" variant="outline" :disabled="saving.rain" @click="checkRain">
              <Spinner v-if="saving.rain" data-icon="inline-start" />지금 우천 알림 확인
            </Button>
            <Button type="submit" :disabled="saving.settings">
              <Spinner v-if="saving.settings" data-icon="inline-start" />설정 저장
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <Card v-if="rules">
      <CardHeader>
        <CardTitle>최종 변경안 승인자</CardTitle>
        <CardDescription>변경안에서 바뀐 요소에 맞춰 체크한 역할의 승인을 모두 받아야 확정됩니다.</CardDescription>
        <CardAction>
          <Button :disabled="saving.rules" @click="saveRules"><Spinner v-if="saving.rules" data-icon="inline-start" />승인자 저장</Button>
        </CardAction>
      </CardHeader>
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent">
              <TableHead class="text-muted-foreground">언제</TableHead>
              <TableHead v-for="r in roleOptions" :key="r.role" class="text-center text-muted-foreground">{{ r.title }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="k in CHANGE_KINDS" :key="k.value">
              <TableCell>
                <div class="font-medium">{{ k.label }}</div>
                <div class="text-xs text-muted-foreground">{{ k.hint }}</div>
              </TableCell>
              <TableCell v-for="r in roleOptions" :key="r.role" class="text-center">
                <input
                  type="checkbox"
                  class="size-4 accent-primary"
                  :aria-label="`${k.label}에 ${r.title} 승인`"
                  :checked="rules[k.value].includes(r.role)"
                  @change="toggleRule(k.value, r.role)"
                />
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <Card v-if="members.length">
      <CardHeader>
        <CardTitle>구성원</CardTitle>
        <CardDescription>관리자 권한을 주거나 회수하고, 프로젝트를 떠난 사람은 탈퇴 처리합니다. 탈퇴한 계정은 로그인과 알림, 연락처에서 빠집니다.</CardDescription>
      </CardHeader>
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent">
              <TableHead class="text-muted-foreground">이름</TableHead>
              <TableHead class="text-muted-foreground">직책</TableHead>
              <TableHead class="text-muted-foreground">연락처</TableHead>
              <TableHead class="text-muted-foreground">권한</TableHead>
              <TableHead class="text-right text-muted-foreground">관리</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="m in activeMembers" :key="m.id">
              <TableCell class="font-medium">{{ m.name }} <span v-if="isMe(m)" class="text-xs text-muted-foreground">(나)</span></TableCell>
              <TableCell>{{ m.title }}</TableCell>
              <TableCell class="mono">{{ m.phone ?? '' }}</TableCell>
              <TableCell><Badge :variant="m.admin ? 'default' : 'secondary'">{{ m.admin ? '관리자' : '일반' }}</Badge></TableCell>
              <TableCell class="text-right whitespace-nowrap">
                <Button size="sm" variant="outline" :disabled="isMe(m)" @click="setAdmin(m, !m.admin)">
                  {{ m.admin ? '관리자 해제' : '관리자 지정' }}
                </Button>
                <template v-if="confirmWithdraw === m.id">
                  <Button size="sm" variant="destructive" class="ml-1.5" @click="withdraw(m)">정말 탈퇴</Button>
                  <Button size="sm" variant="ghost" class="ml-1" @click="confirmWithdraw = null">취소</Button>
                </template>
                <Button v-else size="sm" variant="ghost" class="ml-1.5 text-destructive" :disabled="isMe(m)" @click="confirmWithdraw = m.id">
                  탈퇴
                </Button>
              </TableCell>
            </TableRow>
            <TableRow v-for="m in leftMembers" :key="m.id" class="text-muted-foreground">
              <TableCell>{{ m.name }}</TableCell>
              <TableCell>{{ m.title }}</TableCell>
              <TableCell class="mono">{{ m.phone ?? '' }}</TableCell>
              <TableCell><Badge variant="outline">탈퇴</Badge></TableCell>
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
</template>
