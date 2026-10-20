<script setup>
import { onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { dateTime, ver } from '../format.js'
import { SHOOT_DAY_ID } from '../labels.js'

const KIND_LABELS = { REPLAN: '재계획', ASK: '근거 질문' }

const proposals = ref([])
const tasks = ref([])
const error = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [p, t] = await Promise.all([api(`/proposals?shootDayId=${SHOOT_DAY_ID}`), api('/ai/tasks?mine=true')])
    proposals.value = p ?? []
    tasks.value = t ?? []
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">변경안</h1>
        <p class="page-sub">Agent가 만든 변경안과 내가 요청한 작업을 최신순으로 봅니다.</p>
      </div>
    </div>

    <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>

    <section class="card">
      <h2 class="card-title">변경안 목록</h2>
      <div v-if="proposals.length" class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>버전</th>
              <th>상태</th>
              <th>루프</th>
              <th>점수</th>
              <th>승인</th>
              <th>생성 시각</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in proposals" :key="p.id">
              <td><RouterLink :to="`/proposals/${p.id}`" class="link">변경안 {{ ver(p.versionNo) }}</RouterLink></td>
              <td><StatusBadge :status="p.status" /></td>
              <td>{{ p.loopNo ?? '' }}</td>
              <td class="mono">{{ p.score !== undefined && p.score !== null ? Number(p.score).toFixed(3) : '' }}</td>
              <td>
                <template v-if="p.requiredCount">{{ p.approvedCount }} / {{ p.requiredCount }}</template>
              </td>
              <td class="mono">{{ dateTime(p.createdAt) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!loading" class="empty">아직 만들어진 변경안이 없습니다.</p>
    </section>

    <section class="card">
      <h2 class="card-title">내 Agent 작업</h2>
      <div v-if="tasks.length" class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>작업</th>
              <th>종류</th>
              <th>상태</th>
              <th>질문</th>
              <th>접수 시각</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tasks" :key="t.id">
              <td><RouterLink :to="`/tasks/${t.id}`" class="link">#{{ t.id }}</RouterLink></td>
              <td>{{ KIND_LABELS[t.kind] ?? t.kind }}</td>
              <td><StatusBadge :status="t.status" /></td>
              <td class="wrap">{{ t.question ?? '' }}</td>
              <td class="mono">{{ dateTime(t.createdAt) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!loading" class="empty">요청한 작업이 없습니다.</p>
    </section>
  </div>
</template>
