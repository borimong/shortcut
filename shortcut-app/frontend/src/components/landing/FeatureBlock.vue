<script setup>
import { cn } from '@/lib/utils'

defineProps({
  // 배열로 주면 덩어리 사이에서만 줄을 바꾼다
  title: { type: [String, Array], required: true },
  desc: { type: String, default: '' },
  reverse: Boolean,
})
</script>

<template>
  <section :class="cn('grid items-center gap-7 md:gap-16', reverse ? 'md:grid-cols-[minmax(0,1fr)_minmax(0,300px)]' : 'md:grid-cols-[minmax(0,300px)_minmax(0,1fr)]')">
    <div :class="cn('flex flex-col gap-3', reverse && 'md:order-2')">
      <h2 class="text-[clamp(26px,3vw,34px)] leading-[1.25] font-extrabold tracking-[-0.03em]">
        <template v-for="(part, i) in [].concat(title)" :key="part">{{ i ? ' ' : '' }}<span class="inline-block">{{ part }}</span></template>
      </h2>
      <p v-if="desc" class="text-[17px] leading-[1.7] text-muted-foreground">{{ desc }}</p>
    </div>
    <div class="min-w-0"><slot /></div>
  </section>
</template>
