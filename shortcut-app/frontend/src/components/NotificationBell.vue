<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '../stores/notifications.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime } from '../format.js'

const store = useNotificationStore()
const toast = useToastStore()
const router = useRouter()
const open = ref(false)
const root = ref(null)

const KIND_LABELS = {
  CHANGE_NOTICE: '변경 공지',
  APPROVAL_REQUEST: '승인 요청',
  DECISION: '승인 결과',
  CALLSHEET: '콜시트'
}

async function select(n) {
  try {
    await store.markRead(n)
  } catch (e) {
    toast.error(e)
  }
  open.value = false
  if (n.link) router.push(n.link)
}

async function readAll() {
  try {
    await store.markAllRead()
  } catch (e) {
    toast.error(e)
  }
}

function onOutside(e) {
  if (open.value && root.value && !root.value.contains(e.target)) open.value = false
}

onMounted(() => document.addEventListener('click', onOutside))
onBeforeUnmount(() => document.removeEventListener('click', onOutside))
</script>

<template>
  <div ref="root" class="bell-wrap">
    <button type="button" class="bell" :aria-label="`알림 ${store.unreadCount}건`" @click="open = !open">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      <span v-if="store.unreadCount > 0" class="count">{{ store.unreadCount > 99 ? '99+' : store.unreadCount }}</span>
    </button>
    <div v-if="open" class="dropdown">
      <div class="drop-head">
        <strong>알림</strong>
        <button type="button" class="text-btn" :disabled="store.unreadCount === 0" @click="readAll">모두 읽음</button>
      </div>
      <ul v-if="store.items.length" class="list">
        <li v-for="n in store.items" :key="n.id">
          <button type="button" class="item" :class="{ unread: !n.read }" @click="select(n)">
            <span class="kind">{{ KIND_LABELS[n.kind] ?? n.kind }}</span>
            <span class="title">{{ n.title }}</span>
            <span v-if="n.body" class="body">{{ n.body }}</span>
            <span class="time">{{ dateTime(n.createdAt) }}</span>
          </button>
        </li>
      </ul>
      <p v-else class="empty">새 알림이 없습니다.</p>
    </div>
  </div>
</template>

<style scoped>
.bell-wrap {
  position: relative;
}

.bell {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  color: var(--charcoal);
}

.count {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--bad);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  display: grid;
  place-items: center;
}

.dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 10px);
  width: min(360px, calc(100vw - 32px));
  max-height: 440px;
  overflow-y: auto;
  background: #fff;
  border-radius: var(--radius-card);
  box-shadow: 0 16px 40px rgba(31, 41, 55, 0.16);
  padding: 8px;
}

.drop-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
}

.text-btn {
  border: 0;
  background: none;
  color: var(--text-sub);
  font-size: 13px;
  cursor: pointer;
}

.text-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  width: 100%;
  text-align: left;
  border: 0;
  background: none;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
  color: var(--text-sub);
}

.item:hover {
  background: var(--head-bg);
}

.item.unread {
  color: var(--text);
  background: #f0fbf9;
}

.kind {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--run);
}

.title {
  font-weight: 700;
}

.body {
  font-size: 13px;
}

.time {
  font-size: 12px;
  color: var(--text-faint);
}

@media (max-width: 480px) {
  .dropdown {
    position: fixed;
    left: 16px;
    right: 16px;
    top: 64px;
    width: auto;
  }
}
</style>
