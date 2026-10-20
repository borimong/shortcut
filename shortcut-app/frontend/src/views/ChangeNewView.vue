<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
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
  <div class="page narrow">
    <div class="page-head">
      <div>
        <h1 class="page-title">변경 입력</h1>
        <p class="page-sub">촬영 변수를 입력하면 Agent가 오후 블록을 다시 계획하고 승인 요청까지 올립니다.</p>
      </div>
    </div>

    <form class="card stack" @submit.prevent="submit">
      <div class="field">
        <span class="field-label">변경 유형</span>
        <div class="types">
          <label v-for="t in EVENT_TYPES" :key="t.value" class="type" :class="{ on: type === t.value }">
            <input v-model="type" type="radio" name="type" :value="t.value" />
            {{ t.label }}
          </label>
        </div>
      </div>

      <label class="field">
        <span class="field-label">상세 내용</span>
        <textarea v-model="detail" class="textarea" :placeholder="current?.hint" required></textarea>
      </label>

      <label class="field">
        <span class="field-label">감독 지시 (선택)</span>
        <input v-model="instruction" class="input" placeholder="예: 웃돈을 줘도 좋은 데로" />
      </label>

      <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>

      <div class="row actions">
        <RouterLink to="/" class="btn btn-secondary">취소</RouterLink>
        <button type="submit" class="btn btn-primary" :disabled="busy || !detail.trim()">
          {{ busy ? '접수 중' : '변경 접수하고 재계획 시작' }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.narrow {
  max-width: 760px;
  margin: 0 auto;
}

.types {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.type {
  border: 1.5px solid var(--line);
  border-radius: var(--radius-btn);
  padding: 12px 8px;
  text-align: center;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.type input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.type.on {
  border-color: var(--charcoal);
  background: var(--charcoal);
  color: var(--mint);
}

.type:has(input:focus-visible) {
  outline: 2px solid var(--mint);
  outline-offset: 2px;
}

.actions {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .types {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .actions .btn {
    flex: 1;
  }
}
</style>
