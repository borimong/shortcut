<script setup>
const items = [
  { title: '주 52시간 검사', desc: '스태프별 주간 근무 시간을 넘기는 일정은 제안하지 않습니다.' },
  { title: '배우 계약 조건', desc: '계약서에 적힌 하루 촬영 시간과 제외 조건을 함께 봅니다.' },
  { title: '가능 시간 확인', desc: '배우와 스태프, 장소, 장비가 비는 시간 안에서만 씬을 옮깁니다.' },
  { title: '촬영 허가와 금지 구역', desc: '허가 기간과 드론 비행 금지 구역을 벗어나는 안은 걸러 냅니다.' },
  { title: '예산 한도', desc: '추가 비용이 회차 예산을 넘는 안은 올리지 않습니다.' },
  { title: '근거 조항', desc: '바뀐 씬마다 근거가 된 계약 조항과 규정이 붙어 있습니다.' },
  { title: '미확정 항목', desc: '회신을 기다리는 배우 일정은 확정된 일정과 구분해 둡니다.' },
  { title: '거절 사유 반영', desc: '승인자가 남긴 거절 사유는 다음 안을 짤 때 조건으로 들어갑니다.' },
  { title: '받는 사람별 콜시트', desc: '배우에게는 간단본을, 스태프에게는 상세본을 보냅니다.' },
  { title: '변동 이력', desc: '언제 무엇이 바뀌었고 누가 승인했는지 기록으로 남습니다.' },
]
</script>

<template>
  <section class="border-t py-20 md:py-28">
    <div class="wrap flex flex-col gap-12">
      <h2 class="section-title">세부 기능</h2>
      <ul class="grid grid-cols-1 gap-x-16 md:grid-cols-2">
        <li v-for="it in items" :key="it.title" class="flex flex-col gap-1 border-t py-5">
          <h3 class="text-[17px] font-semibold">{{ it.title }}</h3>
          <p class="text-[15px] leading-relaxed text-muted-foreground">{{ it.desc }}</p>
        </li>
      </ul>
    </div>
  </section>
</template>
