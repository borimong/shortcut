<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import logoUrl from '../assets/logo.webp'
import { Boxes } from '@lucide/vue'
import NotificationBell from './NotificationBell.vue'
import ResourcePanel from './ResourcePanel.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList } from '@/components/ui/navigation-menu'
import { cn } from '@/lib/utils'
import { useAuthStore } from '../stores/auth.js'
import { useNotificationStore } from '../stores/notifications.js'
import { useResourceStore } from '../stores/resources.js'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const resources = useResourceStore()
const notifications = useNotificationStore()
const resourcesOpen = ref(false)

// 헤더 배지가 최신이 되도록 처음에 한 번, 그리고 변경이나 확정 알림이 오면 다시 불러온다.
onMounted(() => resources.load())
watch(
  () => notifications.lastNotification,
  (n) => {
    if (n && ['CHANGE_NOTICE', 'CALLSHEET', 'DECISION'].includes(n.kind)) resources.load()
  }
)

const menu = computed(() =>
  [
    { to: '/board', label: '오늘의 촬영판' },
    { to: '/callsheet', label: '콜시트' },
    auth.canSubmitChange && { to: '/changes/new', label: '변경 입력' },
    { to: '/proposals', label: '변경안' },
    { to: '/history', label: '변동 이력' },
    auth.isAdmin && { to: '/admin', label: '관리자' }
  ].filter(Boolean)
)

const isActive = (to) => route.path.startsWith(to)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <header class="sticky top-0 z-50 border-b bg-background/90 backdrop-blur print:hidden">
    <div class="wrap flex h-16 items-center gap-6">
      <RouterLink to="/board" aria-label="오늘의 촬영판으로 이동">
        <img :src="logoUrl" alt="ShortCut" width="110" height="36" class="h-9 w-auto" />
      </RouterLink>
      <!-- 메뉴가 여섯 개까지 늘어 768px 폭에서는 한 줄에 다 들어가지 않으므로, 한 줄 메뉴는 1024px부터 쓴다 -->
      <NavigationMenu class="hidden lg:flex">
        <NavigationMenuList>
          <NavigationMenuItem v-for="m in menu" :key="m.to">
            <NavigationMenuLink as-child :active="isActive(m.to)">
              <RouterLink :to="m.to" :class="cn('px-3 text-sm whitespace-nowrap', isActive(m.to) && 'text-primary')">{{ m.label }}</RouterLink>
            </NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
      <div class="ml-auto flex shrink-0 items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          class="gap-2"
          :aria-label="`자원 현황, 사용 불가 ${resources.unavailableCount}건`"
          @click="resourcesOpen = true"
        >
          <Boxes data-icon="inline-start" />
          <span class="hidden xl:inline">자원 현황</span>
          <Badge v-if="resources.unavailableCount" variant="destructive" class="h-5 min-w-5 px-1">{{ resources.unavailableCount }}</Badge>
        </Button>
        <NotificationBell />
        <div class="hidden flex-col leading-tight whitespace-nowrap sm:flex">
          <span class="text-sm font-medium">{{ auth.user?.name }}</span>
          <span class="text-xs text-muted-foreground">{{ auth.user?.title }}</span>
        </div>
        <Button variant="outline" size="sm" @click="logout">로그아웃</Button>
      </div>
    </div>
    <nav class="wrap flex gap-1 overflow-x-auto pb-2 lg:hidden" aria-label="화면 메뉴">
      <Button v-for="m in menu" :key="m.to" as-child size="sm" :variant="isActive(m.to) ? 'secondary' : 'ghost'">
        <RouterLink :to="m.to">{{ m.label }}</RouterLink>
      </Button>
    </nav>
    <ResourcePanel v-model:open="resourcesOpen" />
  </header>
</template>
