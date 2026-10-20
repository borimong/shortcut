<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '../api.js'
import { useToastStore } from '../stores/toast.js'
import { EVENT_TYPES, SHOOT_DAY_ID } from '../labels.js'

const router = useRouter()
const toast = useToastStore()

const type = ref('RAIN')
const detail = ref('')
const instruction = ref('')
const busy = ref(false)
const error = ref(null)

const current = computed(() => EVENT_TYPES.find((t) => t.value === type.value))

async function submit() {
  if (busy.value || !detail.value.trim()) return
  busy.value = true
  error.value = null
  try {
    const body = { shootDayId: SHOOT_DAY_ID, type: type.value, detail: detail.value.trim() }
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
                class="grid w-full grid-cols-2 sm:grid-cols-5"
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

            <Field>
              <FieldLabel for="change-detail">상세 내용</FieldLabel>
              <Textarea id="change-detail" v-model="detail" class="min-h-28" :placeholder="current?.hint" required />
            </Field>

            <Field>
              <FieldLabel for="change-instruction">감독 지시 (선택)</FieldLabel>
              <Input id="change-instruction" v-model="instruction" placeholder="웃돈을 줘도 좋은 데로" />
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
          <Button type="submit" class="flex-1 sm:flex-none" :disabled="busy || !detail.trim()">
            <Spinner v-if="busy" data-icon="inline-start" />
            {{ busy ? '접수 중' : '변경 접수하고 재계획 시작' }}
          </Button>
        </CardFooter>
      </Card>
    </form>
  </div>
</template>
