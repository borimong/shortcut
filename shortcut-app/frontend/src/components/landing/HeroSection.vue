<script setup>
import AppFrame from './AppFrame.vue'
import { Button } from '@/components/ui/button'
import proposalDiff from '@/assets/screens/proposal-diff.webp'
</script>

<template>
  <section id="top" class="border-b pt-14 pb-20 md:pt-20 md:pb-28">
    <div class="wrap grid items-center gap-12 lg:grid-cols-2 lg:gap-14">
      <div class="flex flex-col items-start gap-6">
        <h1 class="text-[clamp(32px,3.6vw,46px)] leading-[1.16] font-extrabold tracking-[-0.04em]">
          <span class="inline-block">내일 촬영이 틀어져도</span><br />
          <span class="inline-block">콜시트는 제때 나갑니다</span>
        </h1>
        <p class="lede">특보가 뜨면 새 일정안을 짜고 승인까지 받아 둡니다.</p>
        <Button as-child size="lg" class="mt-2 h-12 px-6 text-base">
          <RouterLink to="/login">데모 시작하기</RouterLink>
        </Button>
      </div>

      <AppFrame
        :src="proposalDiff"
        alt="변경안 화면. 한강 공원 13시 촬영을 파주 세트장 14시로 옮긴 안을 현재 일정과 나란히 비교한다."
        :width="1128"
        :height="669"
        eager
      />
    </div>
  </section>
</template>
