<script setup>
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

const faqs = [
  { q: 'AI가 일정을 마음대로 바꾸나요?', a: '아니요, 필요한 사람이 모두 승인해야 확정됩니다.' },
  { q: '어떤 조건을 지키나요?', a: '배우 계약과 주 52시간, 촬영 허가, 예산 한도를 지킵니다.' },
  { q: '승인은 누가 하나요?', a: '바뀐 내용과 관련된 감독과 팀장만 승인합니다.' },
  { q: '지킬 수 있는 안이 없으면요?', a: '막힌 이유를 정리해 1조감독에게 넘깁니다.' },
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
