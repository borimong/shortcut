<script setup>
import AppFrame from './AppFrame.vue'
import AlertToast from './AlertToast.vue'
import PlanDiff from './PlanDiff.vue'
import { Button } from '@/components/ui/button'
import { project } from '@/data/demo.js'
</script>

<template>
  <section id="top" class="border-b pt-14 pb-20 md:pt-20 md:pb-28">
    <div class="wrap grid items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
      <div class="flex flex-col items-start gap-6">
        <h1 class="text-[clamp(34px,3.9vw,50px)] leading-[1.16] font-extrabold tracking-[-0.04em]">
          <span class="inline-block">내일 촬영이 틀어져도</span><br />
          <span class="inline-block">아침 콜시트는</span> <span class="inline-block">제때 나갑니다</span>
        </h1>
        <p class="lede max-w-[36ch]">
          기상특보나 배우 일정 변경이 생기면 영향받는 씬을 찾아 새 일정안을 만들고, 필요한 감독에게만 승인을 받아 콜시트를 다시 보냅니다.
        </p>
        <div class="mt-2 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Button as-child size="lg" class="h-12 px-6 text-base">
            <RouterLink to="/login">데모 시작하기</RouterLink>
          </Button>
          <a href="#flow" class="text-[15px] font-medium underline decoration-border underline-offset-4 hover:decoration-foreground">작동 순서 보기</a>
        </div>
      </div>

      <figure class="flex min-w-0 flex-col gap-3">
        <AppFrame action="승인 요청">
          <div class="flex flex-col gap-4">
            <AlertToast />
            <PlanDiff :show-evidence="false" />
          </div>
        </AppFrame>
        <figcaption class="text-[13px] text-muted-foreground">가상 {{ project.title }} {{ project.episode }} 데모 화면</figcaption>
      </figure>
    </div>
  </section>
</template>
