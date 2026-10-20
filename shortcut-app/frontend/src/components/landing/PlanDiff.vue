<script setup>
import { ArrowRight, Clock } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { originalPlan, newPlan, evidence, unresolved, planSummary, project } from '@/data/demo.js'

defineProps({ showEvidence: { type: Boolean, default: true } })

// 씬마다 원본과 새 안을 한 줄로 묶어 높이를 맞춘다
const pairs = originalPlan.map((before, i) => ({ before, after: newPlan[i] }))
const cell = 'grid min-w-0 grid-cols-[46px_34px_minmax(0,1fr)] gap-x-2 rounded-md border px-2.5 py-2 text-sm @max-[520px]:grid-cols-[40px_minmax(0,1fr)]'
</script>

<template>
  <div class="@container flex flex-col gap-4">
    <header class="flex flex-wrap items-end justify-between gap-2.5">
      <div>
        <p class="mono flex gap-2 text-xs text-muted-foreground"><span>{{ project.episode }}</span><span>{{ project.shootDate }}</span></p>
        <h3 class="text-xl font-bold">변경안 {{ planSummary.version }}</h3>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <Badge variant="secondary">씬 {{ planSummary.movedScenes }}개 이동</Badge>
        <Badge variant="secondary">추가 비용 {{ planSummary.extraCost }}</Badge>
        <Badge variant="secondary">이동 {{ planSummary.travelSaved }} 감소</Badge>
      </div>
    </header>

    <div class="grid grid-cols-[minmax(0,1fr)_28px_minmax(0,1fr)] gap-x-1 gap-y-1.5 @max-[520px]:grid-cols-[minmax(0,1fr)_18px_minmax(0,1fr)]">
      <p class="text-xs font-semibold text-muted-foreground">원본</p>
      <span />
      <p class="text-xs font-semibold text-muted-foreground">새 안</p>

      <template v-for="{ before, after } in pairs" :key="before.id">
        <div :class="cn(cell, before.outdoor && 'border-warning/40 bg-warning/10')">
          <span class="mono row-span-3 text-[13px] text-muted-foreground">{{ before.start }}</span>
          <span class="mono row-span-3 text-xs text-muted-foreground @max-[520px]:hidden">{{ before.id }}</span>
          <span class="font-semibold">{{ before.title }}</span>
          <span class="flex items-center gap-1.5 text-[13px] text-muted-foreground">
            {{ before.location }}<Badge v-if="before.outdoor" variant="warning" class="text-[11px]">야외</Badge>
          </span>
        </div>
        <span :class="cn('grid place-items-center', after.changes.length ? 'text-primary' : 'text-border')"><ArrowRight class="size-3.5" /></span>
        <div :class="cn(cell, after.changes.length && 'border-primary/40 bg-accent')">
          <span class="mono row-span-3 text-[13px] text-muted-foreground">{{ after.start }}</span>
          <span class="mono row-span-3 text-xs text-muted-foreground @max-[520px]:hidden">{{ after.id }}</span>
          <span class="font-semibold">{{ after.title }}</span>
          <span class="text-[13px] text-muted-foreground">{{ after.location }}</span>
          <span v-if="after.changes.length" class="mt-1 flex flex-wrap gap-1">
            <Badge v-for="c in after.changes" :key="c" variant="outline" class="bg-background text-[11px]">{{ c }}</Badge>
          </span>
        </div>
      </template>
    </div>

    <template v-if="showEvidence">
      <Separator />
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="e in evidence" :key="e.code" variant="outline" class="gap-1.5 py-0.5 pl-1">
          <Badge class="mono h-4 bg-foreground px-1.5 text-[10px] text-background">{{ e.code }}</Badge>{{ e.text }}
        </Badge>
      </div>
      <p v-for="u in unresolved" :key="u" class="flex items-center gap-1.5 text-[13px] text-warning-foreground"><Clock class="size-3.5 shrink-0" /><span class="font-semibold">미확정</span><span>{{ u }}</span></p>
    </template>
  </div>
</template>
