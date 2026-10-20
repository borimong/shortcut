<script setup>
import { Bell } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { notices, originalPlan } from '@/data/demo.js'

const variant = { '거절': 'destructive', '승인 요청': 'info', '변경 공지': 'warning' }
</script>

<template>
  <div class="grid gap-3.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
    <div class="col-span-full flex items-center gap-4 pb-2">
      <span class="font-extrabold tracking-tight">ShortCut</span>
      <nav class="hidden flex-1 gap-4 text-[13px] text-muted-foreground sm:flex">
        <span>오늘의 촬영판</span><span>변경안</span><span>승인 현황</span><span>콜시트</span>
      </nav>
      <span class="relative ml-auto">
        <Bell class="size-5" />
        <Badge variant="destructive" class="absolute -top-2 -right-3 h-4 min-w-4 bg-destructive px-1 text-[10px] text-primary-foreground">{{ notices.length }}</Badge>
      </span>
    </div>
    <Separator class="col-span-full" />

    <div class="hidden flex-col gap-1.5 opacity-80 sm:flex" aria-hidden="true">
      <p class="text-[13px] font-bold text-muted-foreground">7화 촬영판</p>
      <div v-for="s in originalPlan.slice(1, 5)" :key="s.id"
           class="grid grid-cols-[42px_32px_minmax(0,1fr)] items-center gap-x-1.5 rounded-md border px-2 py-1.5 text-[13px]"
           :class="s.outdoor && 'border-warning/40 bg-warning/10'">
        <span class="mono text-xs text-muted-foreground">{{ s.start }}</span>
        <b>{{ s.id }}</b>
        <span class="truncate">{{ s.title }}</span>
        <Badge v-if="s.outdoor" variant="warning" class="col-start-3 mt-0.5 w-fit text-[11px]">특보 영향</Badge>
      </div>
    </div>

    <div class="rounded-md border bg-background px-3 pt-3 pb-2">
      <p class="pb-1 text-[13px] font-semibold">알림 {{ notices.length }}</p>
      <div>
        <template v-for="(n, i) in notices" :key="n.text">
          <Separator v-if="i > 0" />
          <div class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 py-2.5 text-sm">
            <Badge :variant="variant[n.kind]" class="row-span-2 self-start text-[11px]">{{ n.kind }}</Badge>
            <span>{{ n.text }}</span>
            <span class="text-xs text-muted-foreground">{{ n.at }}</span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
