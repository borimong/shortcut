<script setup>
// 특보 감지부터 콜시트 재배포까지 실제 처리 순서. 카드 대신 번호 붙은 한 줄 흐름으로 보여 준다
const steps = [
  { title: '감지', desc: '촬영 장소마다 특보 구역을 30분 간격으로 확인합니다.' },
  { title: '재조정', desc: '계약과 주 52시간, 촬영 허가, 예산을 지키는 일정안을 만듭니다.' },
  { title: '승인', desc: '바뀐 내용과 관련된 감독과 팀장에게만 승인을 받습니다.' },
  { title: '배포', desc: '확정된 콜시트를 다시 보내고 누가 확인했는지 봅니다.' },
]
</script>

<template>
  <section id="flow" class="py-20 md:py-28">
    <div class="wrap flex flex-col gap-12">
      <h2 class="section-title max-w-[18ch]">콜시트가 다시 나가기까지</h2>
      <ol class="grid grid-cols-1 gap-x-8 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
        <li v-for="(s, i) in steps" :key="s.title" class="flex flex-col gap-2 border-t-2 border-foreground pt-4">
          <span class="mono text-sm text-muted-foreground">{{ String(i + 1).padStart(2, '0') }}</span>
          <h3 class="text-xl font-bold tracking-tight">{{ s.title }}</h3>
          <p class="text-[15px] leading-relaxed text-muted-foreground">{{ s.desc }}</p>
        </li>
      </ol>
    </div>
  </section>
</template>
