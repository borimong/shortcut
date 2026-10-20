<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import logoUrl from '../assets/logo.png'
import NotificationBell from './NotificationBell.vue'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const router = useRouter()

const menu = computed(() =>
  [
    { to: '/', label: '오늘의 촬영판' },
    auth.canSubmitChange && { to: '/changes/new', label: '변경 입력' },
    { to: '/proposals', label: '변경안' },
    { to: '/history', label: '변동 이력' }
  ].filter(Boolean)
)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <header class="header">
    <div class="container bar">
      <RouterLink to="/" class="brand" aria-label="오늘의 촬영판으로 이동">
        <img :src="logoUrl" alt="ShortCut" />
      </RouterLink>
      <nav class="menu">
        <RouterLink
          v-for="m in menu"
          :key="m.to"
          :to="m.to"
          class="menu-link"
          :class="{ active: m.to === '/' ? $route.path === '/' : $route.path.startsWith(m.to) }"
        >
          {{ m.label }}
        </RouterLink>
      </nav>
      <div class="right">
        <NotificationBell />
        <div class="who">
          <strong>{{ auth.user?.name }}</strong>
          <span class="muted small">{{ auth.user?.title }}</span>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" @click="logout">로그아웃</button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(31, 41, 55, 0.06);
}

.bar {
  display: flex;
  align-items: center;
  gap: 28px;
  min-height: 64px;
}

.brand {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.brand img {
  height: 28px;
  width: auto;
  display: block;
}

.menu {
  display: flex;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.menu-link {
  padding: 8px 12px;
  border-radius: var(--radius-btn);
  text-decoration: none;
  font-weight: 600;
  color: var(--text-sub);
  white-space: nowrap;
}

.menu-link:hover {
  color: var(--text);
  background: var(--head-bg);
}

.menu-link.active {
  color: var(--mint);
  background: var(--charcoal);
}

.right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.who {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  text-align: right;
}

@media (max-width: 900px) {
  .bar {
    flex-wrap: wrap;
    gap: 10px 16px;
    padding-top: 10px;
  }

  .right {
    margin-left: auto;
  }

  .menu {
    order: 3;
    flex-basis: 100%;
    overflow-x: auto;
    padding-bottom: 8px;
  }
}

@media (max-width: 480px) {
  .who span {
    display: none;
  }

  .right {
    gap: 8px;
  }
}
</style>
