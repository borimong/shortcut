<script setup>
import { Calendar, ChartBar, ChevronRight, FilePen, House, Send, SquareCheck, Zap } from '@lucide/vue'
import Stripboard from './Stripboard.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { approvals, project, planSummary } from '@/data/demo.js'

const done = approvals.filter(a => a.status === 'APPROVED').length
const side = [House, Calendar, FilePen, SquareCheck, Send, ChartBar]
const history = [
  { at: '22:02', text: '특보 감지' },
  { at: '22:06', text: '변경안 v8 생성' },
  { at: '22:17', text: '동시녹음팀장 거절' },
]
const dot = { APPROVED: 'bg-success', PENDING: 'bg-border', REJECTED: 'bg-destructive' }
</script>

<template>
  <Card class="grid min-h-[460px] grid-cols-1 gap-0 overflow-hidden rounded-md py-0 text-[13px] shadow-frame ring-0 sm:grid-cols-[52px_minmax(0,1fr)] lg:grid-cols-[52px_minmax(0,1fr)_220px]" aria-label="ShortCut 일정 화면 미리 보기">
    <aside class="hidden flex-col items-center gap-5 bg-sidebar py-3.5 text-sidebar-foreground sm:flex">
      <span class="mb-2 grid size-7.5 place-items-center rounded-md bg-destructive text-primary-foreground"><Zap class="size-3.5" /></span>
      <component :is="ic" v-for="(ic, i) in side" :key="i" :class="cn('size-4', i === 1 && 'text-sidebar-accent-foreground')" />
    </aside>

    <div class="flex min-w-0 flex-col gap-3 px-4 py-3.5">
      <div class="flex items-center gap-1.5 truncate text-muted-foreground">
        <span class="hidden sm:inline">프로젝트</span><ChevronRight class="hidden size-3 sm:inline" />
        <span class="hidden sm:inline">{{ project.title }}</span><ChevronRight class="hidden size-3 sm:inline" />
        <span class="hidden sm:inline">{{ project.episode }}</span><ChevronRight class="hidden size-3 sm:inline" />
        <b class="text-foreground">촬영 일정</b>
        <Badge variant="info">변경안 {{ planSummary.version }}</Badge>
        <Button size="sm" class="ml-auto">승인 요청</Button>
      </div>
      <Tabs default-value="strip">
        <TabsList>
          <TabsTrigger value="strip">스트립보드</TabsTrigger>
          <TabsTrigger value="calendar">캘린더</TabsTrigger>
          <TabsTrigger value="history">변동 이력</TabsTrigger>
        </TabsList>
        <TabsContent value="strip" class="pt-2"><Stripboard /></TabsContent>
        <TabsContent value="calendar" class="pt-2 text-muted-foreground">캘린더 보기는 데모에서 준비 중입니다.</TabsContent>
        <TabsContent value="history" class="pt-2 text-muted-foreground">
          <ul class="flex flex-col gap-1.5">
            <li v-for="h in history" :key="h.at" class="flex gap-3"><span class="mono">{{ h.at }}</span>{{ h.text }}</li>
          </ul>
        </TabsContent>
      </Tabs>
    </div>

    <aside class="hidden flex-col gap-2.5 border-l bg-muted p-3.5 lg:flex">
      <p class="flex justify-between font-bold">승인 현황 <span class="mono">{{ done }}/{{ approvals.length }}</span></p>
      <Separator />
      <ul class="flex flex-col gap-2">
        <li v-for="a in approvals" :key="a.role" class="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2">
          <span :class="cn('size-2 rounded-full', dot[a.status])" />
          <span>{{ a.role }}</span>
          <span class="mono text-[11px] text-muted-foreground">{{ a.at ?? '' }}</span>
        </li>
      </ul>
      <p class="rounded-md bg-destructive/10 p-2 text-xs leading-normal text-destructive">“성수 스튜디오 오후 공사 소음, 동시녹음 불가”</p>
      <p class="text-xs text-primary">회차 {{ planSummary.round }}/{{ planSummary.maxRound }} 재계획 중</p>
    </aside>
  </Card>
</template>
