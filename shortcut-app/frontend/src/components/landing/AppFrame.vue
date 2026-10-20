<script setup>
import { Card } from '@/components/ui/card'

// 실제 앱 화면을 찍은 이미지를 제품 프레임에 담는다. width/height는 CSS 픽셀 기준이라 레이아웃이 밀리지 않는다.
defineProps({
  src: { type: String, required: true },
  alt: { type: String, required: true },
  width: { type: Number, required: true },
  height: { type: Number, required: true },
  eager: Boolean,
})
</script>

<template>
  <Card class="min-w-0 gap-0 overflow-hidden rounded-md py-0 shadow-frame ring-0">
    <div class="flex items-center gap-1.5 border-b px-3.5 py-2.5" aria-hidden="true">
      <span class="size-2 rounded-full bg-border" />
      <span class="size-2 rounded-full bg-border" />
      <span class="size-2 rounded-full bg-border" />
    </div>
    <img
      :src="src"
      :alt="alt"
      :width="width"
      :height="height"
      :loading="eager ? 'eager' : 'lazy'"
      :fetchpriority="eager ? 'high' : undefined"
      decoding="async"
      class="block h-auto w-full"
    />
  </Card>
</template>
