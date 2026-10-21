<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription } from '@/components/ui/empty'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
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
  CALLSHEET: ['콜시트', 'success']
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
    <PopoverContent align="end" class="w-[min(360px,calc(100vw-32px))] gap-0 p-0">
      <div class="flex items-center justify-between px-4 py-2">
        <h2 class="text-sm font-medium">알림</h2>
        <Button variant="link" size="sm" :disabled="store.unreadCount === 0" @click="readAll">모두 읽음</Button>
      </div>
      <Separator />
      <!-- 스크롤 영역 안쪽 칸은 높이가 정해져야 스크롤되므로 바깥의 최대 높이를 그대로 물려준다 -->
      <ScrollArea
        v-if="store.items.length"
        class="max-h-[min(420px,60vh)] *:data-[slot=scroll-area-viewport]:max-h-[inherit]"
      >
        <ul class="flex flex-col p-1">
          <li v-for="n in store.items" :key="n.id">
            <button type="button" :class="cn('grid w-full grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5 rounded-md px-3 py-2.5 text-left text-sm hover:bg-muted', !n.read && 'bg-accent/60')" @click="select(n)">
              <Badge :variant="KIND[n.kind]?.[1] ?? 'secondary'" class="row-span-3 self-start">{{ KIND[n.kind]?.[0] ?? n.kind }}</Badge>
              <span class="font-medium">{{ n.title }}</span>
              <span v-if="n.body" class="text-muted-foreground">{{ n.body }}</span>
              <span class="text-xs text-muted-foreground">{{ dateTime(n.createdAt) }}</span>
            </button>
          </li>
        </ul>
      </ScrollArea>
      <Empty v-else class="py-8"><EmptyDescription>새 알림이 없습니다.</EmptyDescription></Empty>
    </PopoverContent>
  </Popover>
</template>
