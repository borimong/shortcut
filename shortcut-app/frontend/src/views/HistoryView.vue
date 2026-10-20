<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import { dateTime } from '../format.js'
import { SHOOT_DAY_ID } from '../labels.js'

const items = ref([])
const error = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    items.value = (await api(`/history?shootDayId=${SHOOT_DAY_ID}`)) ?? []
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
        <h1 class="page-title">변동 이력</h1>
        <p class="page-sub">이벤트 접수부터 승인, 재계획 루프, 확정과 배포까지 순서대로 남깁니다.</p>
      </div>
    </div>

    <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>

    <section class="card">
      <ol v-if="items.length" class="timeline">
        <li v-for="(h, i) in items" :key="i">
          <span class="marker"></span>
          <div class="body">
            <div class="row">
              <span class="mono muted">{{ dateTime(h.at) }}</span>
              <span class="badge tone-wait">{{ h.kind }}</span>
            </div>
            <RouterLink v-if="h.link?.startsWith('/')" :to="h.link" class="link">{{ h.text }}</RouterLink>
            <p v-else>{{ h.text }}</p>
          </div>
        </li>
      </ol>
      <p v-else-if="!loading" class="empty">아직 변동 이력이 없습니다.</p>
      <p v-else class="empty">이력을 불러오는 중입니다.</p>
    </section>
  </div>
</template>

<style scoped>
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline li {
  position: relative;
  display: flex;
  gap: 16px;
  padding-bottom: 22px;
}

.timeline li:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 18px;
  bottom: 0;
  width: 2px;
  background: var(--line);
}

.marker {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin-top: 4px;
  border-radius: 50%;
  background: var(--charcoal);
  box-shadow: inset 0 0 0 3px var(--mint);
}

.body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
</style>
