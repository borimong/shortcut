<script setup>
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

// 바뀐 내용에 따라 누가 승인하고 누가 알림만 받는지
const rows = [
  { dept: '제작부', who: '제작 PD', approves: '추가 비용이 생길 때', notices: '승인 요청, 콜시트 확인 현황' },
  { dept: '연출부', who: '연출감독', approves: '장소가 바뀌거나 장면 의도에 영향이 있을 때', notices: '특보 감지, 승인 요청' },
  { dept: '연출부', who: '1조감독, 2조감독', approves: '촬영 순서와 시간, 이동 동선이 바뀔 때', notices: '특보 감지, 재계획이 막힌 이유' },
  { dept: '동시녹음팀', who: '동시녹음팀장', approves: '장소가 바뀌어 소음 확인이 필요할 때', notices: '승인 요청, 바뀐 콜시트' },
  { dept: '촬영팀, 조명팀', who: '촬영감독', approves: '장소나 시간대가 바뀌어 조명 조건이 달라질 때', notices: '승인 요청, 바뀐 콜시트' },
  { dept: '미술팀, 의상분장팀', who: '각 팀장', approves: null, notices: '콜타임 변경, 바뀐 콜시트' },
  { dept: '배우', who: '배우와 매니저', approves: null, notices: '간단본 콜시트 (문자)' },
]
</script>

<template>
  <section class="border-t py-20 md:py-28">
    <div class="wrap flex flex-col gap-10">
      <h2 class="section-title">부서마다 받는 요청이 다릅니다</h2>
      <Table class="min-w-[640px] text-[15px]">
        <TableHeader>
          <TableRow class="hover:bg-transparent">
            <TableHead class="w-[26%]">부서</TableHead>
            <TableHead class="w-[42%]">승인하는 변경</TableHead>
            <TableHead>받는 알림</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="r in rows" :key="r.dept + r.who" class="hover:bg-transparent">
            <TableCell class="py-4 align-top whitespace-normal">
              <span class="font-medium">{{ r.dept }}</span>
              <span class="block text-[13px] text-muted-foreground">{{ r.who }}</span>
            </TableCell>
            <TableCell class="py-4 align-top whitespace-normal" :class="!r.approves && 'text-muted-foreground'">
              {{ r.approves ?? '승인하지 않음' }}
            </TableCell>
            <TableCell class="py-4 align-top whitespace-normal text-muted-foreground">{{ r.notices }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </section>
</template>
