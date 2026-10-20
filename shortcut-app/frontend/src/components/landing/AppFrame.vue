<script setup>
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

defineProps({ action: { type: String, default: '' } })
</script>

<template>
  <Card class="min-w-0 gap-0 overflow-hidden rounded-md py-0 shadow-frame ring-0">
    <CardHeader class="flex flex-row items-center gap-3 border-b px-4 py-3">
      <div class="flex flex-1 flex-col gap-1.5">
        <Skeleton class="h-1.5 w-30 animate-none" />
        <Skeleton class="h-1.5 w-18 animate-none" />
      </div>
      <Button v-if="action" size="sm">{{ action }}</Button>
    </CardHeader>
    <CardContent class="p-4 sm:p-5">
      <slot />
    </CardContent>
  </Card>
</template>
