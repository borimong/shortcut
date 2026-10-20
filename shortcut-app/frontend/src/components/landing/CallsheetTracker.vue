<script setup>
import { Check, X } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { recipients, deliveryStats, project } from '@/data/demo.js'

const stats = [
  { label: '보냄', value: deliveryStats.sent },
  { label: '반송', value: deliveryStats.bounced, bad: true },
  { label: '열람', value: deliveryStats.viewed },
  { label: '확인', value: deliveryStats.confirmed },
]
</script>

<template>
  <div class="flex flex-col gap-3">
    <header class="flex items-baseline justify-between gap-2">
      <h3 class="text-lg font-bold">{{ project.episode }} 확정 콜시트</h3>
      <Badge class="mono bg-foreground text-background">CALL {{ project.callTime }}</Badge>
    </header>
    <dl class="grid grid-cols-4 divide-x rounded-md border">
      <div v-for="s in stats" :key="s.label" class="flex flex-col px-3 py-2.5">
        <dt class="order-last text-xs text-muted-foreground">{{ s.label }}</dt>
        <dd :class="['mono text-2xl leading-tight font-semibold', s.bad && 'text-destructive']">{{ s.value }}</dd>
      </div>
    </dl>
    <Table>
      <TableHeader>
        <TableRow><TableHead>받는 사람</TableHead><TableHead>채널</TableHead><TableHead>열람</TableHead><TableHead>확인</TableHead></TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-for="r in recipients" :key="r.name">
          <TableCell><b>{{ r.name }}</b><br /><span class="text-xs text-muted-foreground">{{ r.role }}</span></TableCell>
          <TableCell>{{ r.channel }}</TableCell>
          <TableCell>
            <Badge v-if="r.delivery === 'BOUNCED'" variant="destructive">반송</Badge>
            <span v-else-if="r.viewedAt" class="mono flex items-center gap-1 text-[13px] text-success"><Check class="size-3.5" />{{ r.viewedAt }}</span>
            <X v-else class="size-4 text-destructive" />
          </TableCell>
          <TableCell>
            <span v-if="r.confirmedAt" class="mono flex items-center gap-1 text-[13px] text-success"><Check class="size-3.5" />{{ r.confirmedAt }}</span>
            <span v-else class="text-muted-foreground">–</span>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </div>
</template>
