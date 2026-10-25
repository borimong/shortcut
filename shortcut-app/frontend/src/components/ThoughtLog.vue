<script setup>
import { ref } from 'vue'
import { MessageSquareWarning } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { api } from '../api.js'
import { useToastStore } from '../stores/toast.js'
import { AGENTS, NODE_LABELS } from '../labels.js'

// entries는 THOUGHT와 REVISION 이벤트를 받은 순서대로 담는다. { kind, id, ...payload }
const props = defineProps({
  taskId: { type: [String, Number], required: true },
  status: { type: String, default: '' },
  entries: { type: Array, required: true }
})
const emit = defineEmits(['revised'])
const toast = useToastStore()

const editing = ref(null)
const comment = ref('')
const sending = ref(false)

// 계획 단계 생각은 승인 대기 중에만, 실행 단계 생각은 실행이 끝난 뒤에만 고칠 수 있다(그래프가 멈춰 있어야 분기할 수 있다).
function blockedReason(e) {
  if (e.id === null || e.id === undefined) return '이벤트 번호가 없어 고칠 수 없습니다.'
  if (e.phase === 'exec') {
    return ['DONE', 'NEEDS_HUMAN'].includes(props.status) ? '' : '실행이 끝난 뒤에 고칠 수 있습니다.'
  }
  return props.status === 'WAITING_APPROVAL' ? '' : '승인 대기 중에만 고칠 수 있습니다.'
}

function open(e) {
  editing.value = e.id
  comment.value = ''
}

async function submit(e) {
  const text = comment.value.trim()
  if (!text) return
  sending.value = true
  try {
    const res = await api(`/ai/tasks/${props.taskId}/revisions`, { method: 'POST', body: { eventId: e.id, comment: text } })
    editing.value = null
    comment.value = ''
    toast.info(e.phase === 'exec' ? '수정 요청을 보냈습니다. 해당 Agent가 다시 일합니다.' : '수정 요청을 보냈습니다. 그 판단부터 다시 계획합니다.')
    emit('revised', res ?? { phase: e.phase })
  } catch (err) {
    toast.error(err)
  } finally {
    sending.value = false
  }
}

const agentLabel = (name) => AGENTS[name]?.label ?? name ?? 'Agent'
const nodeLabel = (node) => NODE_LABELS[node] ?? node
</script>

<template>
  <ol v-if="entries.length" class="flex max-h-[640px] flex-col gap-2 overflow-y-auto">
    <li v-for="e in entries" :key="`${e.kind}-${e.id}`">
      <div v-if="e.kind === 'revision'" class="flex flex-wrap items-center gap-2 rounded-md bg-warning/15 px-3 py-2 text-sm">
        <MessageSquareWarning class="size-4 shrink-0" />
        <span class="font-medium">수정 요청</span>
        <span class="text-muted-foreground">{{ agentLabel(e.agent) }}, {{ nodeLabel(e.node) }}</span>
        <span class="basis-full break-words">{{ e.comment }}</span>
      </div>

      <article v-else class="flex flex-col gap-2 rounded-lg border border-border p-3">
        <header class="flex flex-wrap items-center gap-2">
          <Badge :variant="e.phase === 'exec' ? 'brand' : 'info'">{{ agentLabel(e.agent) }}</Badge>
          <span class="text-sm font-medium">{{ nodeLabel(e.node) }}</span>
          <span class="text-xs text-muted-foreground">{{ e.phase === 'exec' ? '실행 단계' : '계획 단계' }}<template v-if="e.loop">, 루프 {{ e.loop }}</template></span>
          <span class="mono ml-auto text-xs text-muted-foreground">#{{ e.step }}</span>
        </header>
        <dl class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
          <dt class="text-muted-foreground">관찰</dt>
          <dd class="break-words">{{ e.observation }}</dd>
          <dt class="text-muted-foreground">판단</dt>
          <dd class="font-medium break-words">{{ e.decision }}</dd>
          <dt class="text-muted-foreground">이유</dt>
          <dd class="break-words">{{ e.reason }}</dd>
        </dl>

        <template v-if="e.revisable">
          <form v-if="editing === e.id" class="flex flex-col gap-2 sm:flex-row" @submit.prevent="submit(e)">
            <Input v-model="comment" maxlength="300" placeholder="어떻게 바꾸면 좋을지 한 줄로 적어 주세요" autofocus class="flex-1" />
            <div class="flex gap-2">
              <Button type="submit" size="sm" :disabled="sending || !comment.trim()">
                <Spinner v-if="sending" data-icon="inline-start" />보내기
              </Button>
              <Button type="button" size="sm" variant="ghost" @click="editing = null">취소</Button>
            </div>
          </form>
          <div v-else class="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" :disabled="!!blockedReason(e)" @click="open(e)">이 판단 수정 요청</Button>
            <span v-if="blockedReason(e)" class="text-xs text-muted-foreground">{{ blockedReason(e) }}</span>
          </div>
        </template>
      </article>
    </li>
  </ol>
  <p v-else class="text-sm text-muted-foreground">아직 생각 기록이 없습니다.</p>
</template>
