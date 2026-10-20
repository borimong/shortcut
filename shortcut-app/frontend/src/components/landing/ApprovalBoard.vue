<script setup>
import { Lock, RefreshCw } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { approvals, planSummary } from '@/data/demo.js'

const done = approvals.filter(a => a.status === 'APPROVED').length
const status = {
  APPROVED: { label: '승인', variant: 'success' },
  PENDING: { label: '대기', variant: 'secondary' },
  REJECTED: { label: '거절', variant: 'destructive' },
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <header class="flex flex-wrap items-baseline justify-between gap-2">
      <h3 class="text-lg font-bold">변경안 {{ planSummary.version }} 승인 현황</h3>
      <span class="mono text-sm text-muted-foreground">{{ done }} / {{ approvals.length }} 완료</span>
    </header>
    <Progress :model-value="Math.round((done / approvals.length) * 100)" />

    <Table>
      <TableHeader>
        <TableRow><TableHead>승인자</TableHead><TableHead class="max-[560px]:hidden">담당 범위</TableHead><TableHead>상태</TableHead><TableHead class="text-right max-[560px]:hidden">시각</TableHead></TableRow>
      </TableHeader>
      <TableBody>
        <template v-for="a in approvals" :key="a.role">
          <TableRow :class="a.status === 'REJECTED' && 'border-b-0 bg-destructive/5'">
            <TableCell><b>{{ a.role }}</b><br /><span class="text-xs text-muted-foreground">{{ a.department }}</span></TableCell>
            <TableCell class="text-muted-foreground max-[560px]:hidden">{{ a.scope }}</TableCell>
            <TableCell><Badge :variant="status[a.status].variant">{{ status[a.status].label }}</Badge></TableCell>
            <TableCell class="mono text-right text-xs text-muted-foreground max-[560px]:hidden">{{ a.at ?? '–' }}</TableCell>
          </TableRow>
          <TableRow v-if="a.reason" class="bg-destructive/5 hover:bg-destructive/5">
            <TableCell colspan="4" class="pt-0 text-[13px] whitespace-normal text-destructive">“{{ a.reason }}”</TableCell>
          </TableRow>
        </template>
      </TableBody>
    </Table>

    <Alert class="border-primary/30 bg-accent">
      <RefreshCw />
      <AlertDescription class="text-accent-foreground">거절 사유를 조건에 넣어 다시 짜는 중입니다 ({{ planSummary.round }}/{{ planSummary.maxRound }}회차)</AlertDescription>
    </Alert>
    <p class="flex items-center gap-1.5 text-[13px] text-muted-foreground"><Lock class="size-3.5" /> 전원 승인 전에는 콜시트를 보내지 않습니다</p>
  </div>
</template>
