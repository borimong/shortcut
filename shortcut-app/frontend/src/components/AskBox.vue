<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { api } from '../api.js'
import { openStream } from '../sse.js'

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
  <section class="card">
    <h2 class="card-title">근거 질문</h2>
    <form class="ask" @submit.prevent="ask">
      <input
        v-model="question"
        class="input"
        placeholder="예: 파주 세트장에서 드론을 못 쓰는 근거가 뭐야?"
        :disabled="busy"
      />
      <button type="submit" class="btn btn-primary" :disabled="busy || !question.trim()">질문</button>
    </form>

    <div v-if="asked" class="answer-box">
      <p class="q">{{ asked }}</p>
      <p v-if="activity" class="muted small">{{ activity }}</p>
      <p v-if="text" class="a">{{ text }}<span v-if="busy" class="caret"></span></p>
      <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>
      <div v-if="sources.length" class="sources">
        <p class="eyebrow">출처</p>
        <ul>
          <li v-for="s in sources" :key="s.docId">
            <strong>{{ s.title }}</strong> <span class="mono muted">{{ s.docId }}</span>
            <p v-if="s.snippet" class="muted small">{{ s.snippet }}</p>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ask {
  display: flex;
  gap: 8px;
}

.ask .input {
  flex: 1;
  min-width: 0;
}

.answer-box {
  margin-top: 16px;
  padding: 16px;
  border-radius: 12px;
  background: var(--head-bg);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.q {
  font-weight: 700;
}

.a {
  white-space: pre-wrap;
  line-height: 1.7;
}

.sources ul {
  margin: 6px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
