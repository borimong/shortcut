<script setup>
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

const faqs = [
  { q: '기상특보는 어디서 받아 오나요?', a: '기상청 기상특보를 촬영 장소의 특보 구역 기준으로 30분마다 확인합니다. 호우, 강풍, 태풍 특보가 발효되면 그 시간대에 잡힌 야외 씬을 옮깁니다.' },
  { q: 'AI가 일정을 마음대로 바꾸나요?', a: '아닙니다. ShortCut은 변경안을 제안만 합니다. 필요한 부서 승인자가 모두 승인하기 전에는 일정을 확정하거나 콜시트를 보내지 않습니다.' },
  { q: '어떤 규칙을 검사하나요?', a: '배우 계약 조건과 주 52시간, 촬영 허가, 회차 예산 한도, 촬영 금지 구역, 기상특보를 봅니다. 배우와 스태프, 장소, 장비가 그 시간에 실제로 비는지도 함께 확인합니다.' },
  { q: '승인은 누가 하나요?', a: '바뀐 내용에 따라 정해집니다. 장소가 바뀌면 연출감독과 동시녹음팀장, 추가 비용이 생기면 제작 PD에게 승인을 요청합니다.' },
  { q: '조건을 모두 지키는 안이 없으면 어떻게 되나요?', a: '정해진 횟수 안에서 다시 짜 보고, 그래도 어려우면 막힌 이유와 대안을 정리해 1조감독에게 넘깁니다.' },
  { q: '엑셀 일촬표를 가져올 수 있나요?', a: '지금 데모에서는 아직 지원하지 않습니다. 대신 가상 드라마 7화 촬영일 데이터로 전체 흐름을 해 볼 수 있습니다.' },
]
</script>

<template>
  <section id="faq" class="border-t py-20 md:py-28">
    <div class="wrap grid items-start gap-6 md:grid-cols-[minmax(0,300px)_minmax(0,1fr)] md:gap-20">
      <h2 class="section-title">자주 묻는 질문</h2>
      <Accordion type="multiple" collapsible>
        <AccordionItem v-for="(f, i) in faqs" :key="f.q" :value="String(i)">
          <AccordionTrigger class="py-5 text-base font-semibold">{{ f.q }}</AccordionTrigger>
          <AccordionContent class="pb-5 text-[15px] leading-relaxed text-muted-foreground">{{ f.a }}</AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  </section>
</template>
