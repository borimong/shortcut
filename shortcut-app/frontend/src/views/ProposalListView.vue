<script setup>
import { onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api.js'
import { dateTime, ver } from '../format.js'
import { useShootDayStore } from '../stores/shootDay.js'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription } from '@/components/ui/empty'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const KIND_LABELS = { REPLAN: '재계획', ASK: '근거 질문' }

const shootDay = useShootDayStore()

const proposals = ref([])
const tasks = ref([])
const error = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [p, t] = await Promise.all([
      shootDay.ensure().then((id) => api(`/proposals?shootDayId=${id}`)),
      api('/ai/tasks?mine=true')
    ])
    proposals.value = p ?? []
    tasks.value = t ?? []
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page">
    <div class="flex flex-col gap-1">
      <h1 class="page-title">변경안</h1>
      <p class="text-muted-foreground">Agent가 만든 변경안과 내가 요청한 작업을 최신순으로 보여 줍니다.</p>
    </div>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>변경안 목록</CardTitle>
      </CardHeader>
      <CardContent>
        <div v-if="proposals.length" class="overflow-hidden rounded-lg border border-border">
          <Table>
            <TableHeader class="bg-muted">
              <TableRow>
                <TableHead>버전</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>루프</TableHead>
                <TableHead>점수</TableHead>
                <TableHead>승인</TableHead>
                <TableHead>생성 시각</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="p in proposals" :key="p.id">
                <TableCell>
                  <RouterLink :to="`/proposals/${p.id}`" class="font-medium underline underline-offset-3">변경안 {{ ver(p.versionNo) }}</RouterLink>
                </TableCell>
                <TableCell><StatusBadge :status="p.status" /></TableCell>
                <TableCell class="mono">{{ p.loopNo ?? '' }}</TableCell>
                <TableCell class="mono">{{ p.score !== undefined && p.score !== null ? Number(p.score).toFixed(3) : '' }}</TableCell>
                <TableCell class="mono">
                  <template v-if="p.requiredCount">{{ p.approvedCount }} / {{ p.requiredCount }}</template>
                </TableCell>
                <TableCell class="mono">{{ dateTime(p.createdAt) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
        <Empty v-else-if="!loading">
          <EmptyDescription>아직 만들어진 변경안이 없습니다.</EmptyDescription>
        </Empty>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>내 Agent 작업</CardTitle>
      </CardHeader>
      <CardContent>
        <div v-if="tasks.length" class="overflow-hidden rounded-lg border border-border">
          <Table>
            <TableHeader class="bg-muted">
              <TableRow>
                <TableHead>작업</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>질문</TableHead>
                <TableHead>접수 시각</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="t in tasks" :key="t.id">
                <TableCell>
                  <RouterLink :to="`/tasks/${t.id}`" class="mono font-medium underline underline-offset-3">#{{ t.id }}</RouterLink>
                </TableCell>
                <TableCell>{{ KIND_LABELS[t.kind] ?? t.kind }}</TableCell>
                <TableCell><StatusBadge :status="t.status" /></TableCell>
                <TableCell class="min-w-45 whitespace-normal">{{ t.question ?? '' }}</TableCell>
                <TableCell class="mono">{{ dateTime(t.createdAt) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
        <Empty v-else-if="!loading">
          <EmptyDescription>요청한 작업이 없습니다.</EmptyDescription>
        </Empty>
      </CardContent>
    </Card>
  </div>
</template>
