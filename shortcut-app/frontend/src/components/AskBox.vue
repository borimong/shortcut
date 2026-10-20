<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { api } from '../api.js'
import { openStream } from '../sse.js'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps({ proposalId: { type: Number, required: true } })

const question = ref('')
const asked = ref('')
const text = ref('')
const sources = ref([])
const activity = ref('')
const error = ref(null)
const busy = ref(false)
let source = null

function finish() {
  busy.value = false
  activity.value = ''
}

async function ask() {
  const q = question.value.trim()
  if (!q || busy.value) return
  source?.close()
  busy.value = true
  asked.value = q
  text.value = ''
  sources.value = []
  error.value = null
  activity.value = '질문을 접수하는 중'
  try {
    const { taskId } = await api('/ai/tasks', { method: 'POST', body: { question: q, proposalId: props.proposalId } })
    question.value = ''
    activity.value = '근거를 찾는 중'
    source = openStream(`/ai/tasks/${taskId}/stream`, {
      TOOL_START(p) {
        activity.value = `${p.tool} 조회 중`
      },
      TOKEN(p) {
        activity.value = ''
        text.value += p.text ?? ''
      },
      DONE(p) {
        if (!text.value && p.answer) text.value = p.answer
        sources.value = p.sources ?? []
        finish()
      },
      FAILED(p) {
        error.value = { message: p.error ?? '답변을 만들지 못했습니다.' }
        finish()
      },
      NEEDS_HUMAN(p) {
        if (!text.value) text.value = p.reason ?? ''
        finish()
      }
    })
  } catch (e) {
    error.value = e
    finish()
  }
}

onBeforeUnmount(() => source?.close())
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>근거 질문</CardTitle>
    </CardHeader>
    <CardContent class="flex flex-col gap-4">
      <form class="flex gap-2" @submit.prevent="ask">
        <Input
          v-model="question"
          class="min-w-0 flex-1"
          placeholder="예: 파주 세트장에서 드론을 못 쓰는 근거가 뭐야?"
          :disabled="busy"
        />
        <Button type="submit" :disabled="busy || !question.trim()">질문</Button>
      </form>

      <template v-if="asked">
        <Separator />
        <section class="flex flex-col gap-2">
          <p class="font-medium">{{ asked }}</p>
          <p v-if="activity" class="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner />
            {{ activity }}
          </p>
          <p v-if="text" class="leading-relaxed whitespace-pre-wrap">{{ text }}<span v-if="busy" class="ml-0.5 inline-block h-[1em] w-2 animate-pulse bg-foreground align-text-bottom"></span></p>
          <Alert v-if="error" variant="destructive">
            <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
          </Alert>
          <div v-if="sources.length" class="mt-1 flex flex-col gap-1.5">
            <h3 class="text-sm font-medium">출처</h3>
            <ul class="flex list-disc flex-col gap-1.5 pl-5 text-sm">
              <li v-for="s in sources" :key="s.docId">
                {{ s.title }} <span class="mono text-muted-foreground">{{ s.docId }}</span>
                <p v-if="s.snippet" class="text-muted-foreground">{{ s.snippet }}</p>
              </li>
            </ul>
          </div>
        </section>
      </template>
    </CardContent>
  </Card>
</template>
