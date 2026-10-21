<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription } from '@/components/ui/empty'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useNotificationStore } from '../stores/notifications.js'
import { useToastStore } from '../stores/toast.js'
import { dateTime } from '../format.js'

const store = useNotificationStore()
const toast = useToastStore()
const router = useRouter()
const open = ref(false)

const KIND = {
  CHANGE_NOTICE: ['변경 공지', 'warning'],
  APPROVAL_REQUEST: ['승인 요청', 'info'],
  DECISION: ['승인 결과', 'secondary'],
  CALLSHEET: ['콜시트', 'success'],
  WEATHER: ['우천 알림', 'destructive']
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
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button variant="outline" size="icon" class="relative rounded-full" :aria-label="`알림 ${store.unreadCount}건`">
        <Bell />
        <Badge v-if="store.unreadCount > 0" class="absolute -top-1.5 -right-1.5 h-5 min-w-5 bg-destructive px-1 text-[11px] text-primary-foreground">
          {{ store.unreadCount > 99 ? '99+' : store.unreadCount }}
        </Badge>
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" class="flex max-h-[min(560px,calc(100vh-96px))] w-[min(380px,calc(100vw-32px))] flex-col overflow-hidden p-0">
      <div class="flex items-center justify-between px-4 py-3">
        <h2 class="text-sm font-medium">알림</h2>
        <Button variant="link" size="sm" :disabled="store.unreadCount === 0" @click="readAll">모두 읽음</Button>
      </div>
      <Separator />
      <!-- 알림이 많아도 창 밖으로 넘치지 않게 목록만 스크롤한다. -->
      <div v-if="store.items.length" class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <ul class="flex flex-col p-1">
          <li v-for="n in store.items" :key="n.id">
            <button type="button" :class="cn('grid w-full grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5 rounded-md px-3 py-2.5 text-left text-sm break-words [overflow-wrap:anywhere] hover:bg-muted', !n.read && 'bg-accent/60')" @click="select(n)">
              <Badge :variant="KIND[n.kind]?.[1] ?? 'secondary'" class="row-span-3 self-start">{{ KIND[n.kind]?.[0] ?? n.kind }}</Badge>
              <span class="font-medium">{{ n.title }}</span>
              <span v-if="n.body" class="text-muted-foreground">{{ n.body }}</span>
              <span class="text-xs text-muted-foreground">{{ dateTime(n.createdAt) }}</span>
            </button>
          </li>
        </ul>
      </div>
      <Empty v-else class="py-8"><EmptyDescription>새 알림이 없습니다.</EmptyDescription></Empty>
    </PopoverContent>
  </Popover>
</template>
