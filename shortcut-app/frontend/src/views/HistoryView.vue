<script setup>
import { onMounted, ref } from 'vue'
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from '@/components/ui/empty'
import { Spinner } from '@/components/ui/spinner'
import { api } from '../api.js'
import { dateTime } from '../format.js'
import { useShootDayStore } from '../stores/shootDay.js'

const shootDay = useShootDayStore()

const items = ref([])
const error = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    items.value = (await api(`/history?shootDayId=${await shootDay.ensure()}`)) ?? []
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div>
      <h1 class="page-title">변동 이력</h1>
      <p class="mt-1 text-muted-foreground">변경 접수부터 재계획, 승인, 확정과 배포까지 일어난 순서대로 기록됩니다.</p>
    </div>

    <Alert v-if="error" variant="destructive">
      <CircleAlert />
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>

    <Card>
      <CardContent>
        <ol v-if="items.length" class="flex flex-col">
          <li
            v-for="(h, i) in items"
            :key="i"
            class="relative flex gap-4 pb-5.5 not-last:before:absolute not-last:before:top-4.5 not-last:before:bottom-0 not-last:before:left-1.5 not-last:before:w-0.5 not-last:before:bg-border"
          >
            <span class="mt-1 size-3.5 shrink-0 rounded-full border-2 border-muted-foreground/40 bg-background"></span>
            <div class="flex min-w-0 flex-col gap-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="mono text-sm text-muted-foreground">{{ dateTime(h.at) }}</span>
                <Badge variant="secondary">{{ h.kind }}</Badge>
              </div>
              <RouterLink
                v-if="h.link?.startsWith('/')"
                :to="h.link"
                class="text-foreground underline underline-offset-4 hover:text-primary"
              >
                {{ h.text }}
              </RouterLink>
              <p v-else>{{ h.text }}</p>
            </div>
          </li>
        </ol>
        <Empty v-else-if="!loading" class="p-4">
          <EmptyHeader>
            <EmptyDescription>아직 변동 이력이 없습니다.</EmptyDescription>
          </EmptyHeader>
        </Empty>
        <Empty v-else class="p-4">
          <EmptyHeader>
            <EmptyMedia variant="icon"><Spinner /></EmptyMedia>
            <EmptyDescription>이력을 불러오는 중입니다.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </CardContent>
    </Card>
  </div>
</template>
