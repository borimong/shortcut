<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import logoUrl from '../assets/logo.png'
import NotificationBell from './NotificationBell.vue'
import { Button } from '@/components/ui/button'
import { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList } from '@/components/ui/navigation-menu'
import { cn } from '@/lib/utils'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

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
        <img :src="logoUrl" alt="ShortCut" class="h-9 w-auto" />
      </RouterLink>
      <NavigationMenu class="hidden md:flex">
        <NavigationMenuList>
          <NavigationMenuItem v-for="m in menu" :key="m.to">
            <NavigationMenuLink as-child :active="isActive(m.to)">
              <RouterLink :to="m.to" :class="cn('px-3 text-sm', isActive(m.to) && 'text-primary')">{{ m.label }}</RouterLink>
            </NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
      <div class="ml-auto flex items-center gap-3">
        <NotificationBell />
        <div class="hidden flex-col leading-tight sm:flex">
          <span class="text-sm font-medium">{{ auth.user?.name }}</span>
          <span class="text-xs text-muted-foreground">{{ auth.user?.title }}</span>
        </div>
        <Button variant="outline" size="sm" @click="logout">로그아웃</Button>
      </div>
    </div>
    <nav class="wrap flex gap-1 overflow-x-auto pb-2 md:hidden" aria-label="화면 메뉴">
      <Button v-for="m in menu" :key="m.to" as-child size="sm" :variant="isActive(m.to) ? 'secondary' : 'ghost'">
        <RouterLink :to="m.to">{{ m.label }}</RouterLink>
      </Button>
    </nav>
  </header>
</template>
