<script setup>
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import { useAuthStore } from './stores/auth.js'
import { useNotificationStore } from './stores/notifications.js'
import { useToastStore } from './stores/toast.js'

const route = useRoute()
const auth = useAuthStore()
const notifications = useNotificationStore()
const toast = useToastStore()

watch(
  () => auth.token,
  (token) => {
    if (token) {
      notifications.refresh().catch(toast.error)
      notifications.connect()
    } else {
      notifications.disconnect()
    }
  },
  { immediate: true }
)
</script>

<template>
  <!-- 랜딩은 자체 메뉴와 전체 폭 레이아웃을 쓴다 -->
  <RouterView v-if="route.meta.landing" />
  <template v-else>
    <AppHeader v-if="auth.isLoggedIn && route.name !== 'login'" />
    <main class="wrap">
      <RouterView />
    </main>
  </template>
  <ToastHost />
</template>
