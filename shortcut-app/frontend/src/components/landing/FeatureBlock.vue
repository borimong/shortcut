<script setup>
import { cn } from '@/lib/utils'

defineProps({ title: { type: String, required: true }, reverse: Boolean })
</script>

<template>
  <section :class="cn('grid items-center gap-7 md:gap-16', reverse ? 'md:grid-cols-[minmax(0,1fr)_minmax(0,340px)]' : 'md:grid-cols-[minmax(0,340px)_minmax(0,1fr)]')">
    <div :class="cn('flex flex-col gap-3.5', reverse && 'md:order-2')">
      <h2 class="text-[clamp(26px,3vw,34px)] leading-[1.25] font-extrabold tracking-[-0.03em]">{{ title }}</h2>
      <div class="flex flex-col gap-3 text-[17px] leading-[1.8] text-muted-foreground"><slot name="text" /></div>
    </div>
    <div class="min-w-0"><slot /></div>
  </section>
</template>
