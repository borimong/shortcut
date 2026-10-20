<script setup>
import SiteNav from '@/components/landing/SiteNav.vue'
import HeroSection from '@/components/landing/HeroSection.vue'
import FeatureBlock from '@/components/landing/FeatureBlock.vue'
import AppFrame from '@/components/landing/AppFrame.vue'
import ProductWalkthrough from '@/components/landing/ProductWalkthrough.vue'
import FaqSection from '@/components/landing/FaqSection.vue'
import SiteFooter from '@/components/landing/SiteFooter.vue'
import { Button } from '@/components/ui/button'
import changeNew from '@/assets/screens/change-new.webp'
import taskTimeline from '@/assets/screens/task-timeline.webp'
import proposalReview from '@/assets/screens/proposal-review.webp'
import proposalApprovals from '@/assets/screens/proposal-approvals.webp'
import bell from '@/assets/screens/bell.webp'
</script>

<template>
  <SiteNav />
  <main>
    <HeroSection />

    <div id="features" class="wrap grid gap-24 py-22 md:gap-36 md:py-32">
      <FeatureBlock :title="['상황만 적으면', '접수가 끝납니다']" desc="유형을 고르고 몇 줄만 쓰면 됩니다.">
        <AppFrame
          :src="changeNew"
          alt="변경 입력 화면. 우천을 고르고 상세 내용에 강수확률이 80%로 올랐다고 적었다."
          :width="824"
          :height="550"
        />
      </FeatureBlock>

      <FeatureBlock :title="['다시 짜는 과정이', '그대로 보입니다']" desc="단계마다 무엇을 확인했는지 남깁니다." reverse>
        <AppFrame
          :src="taskTimeline"
          alt="재계획 진행 화면. 변경 감지부터 공지까지 열 단계를 마쳤고 오른쪽에 도구 호출 기록이 있다."
          :width="1128"
          :height="836"
        />
      </FeatureBlock>

      <FeatureBlock :title="['올리기 전에', '스스로 채점합니다']" desc="근거와 위험을 100점 만점으로 봅니다.">
        <AppFrame
          :src="proposalReview"
          alt="자체 검토 화면. 76점을 받았고 실행 위험, 하드 제약 근거 같은 항목별 점수가 막대로 나온다."
          :width="1128"
          :height="372"
        />
      </FeatureBlock>

      <FeatureBlock :title="['관련된 사람만', '승인합니다']" desc="누가 승인했고 누가 남았는지 보입니다." reverse>
        <AppFrame
          :src="proposalApprovals"
          alt="승인 현황 화면. 연출감독, 1조감독, 동시녹음팀장, 촬영감독이 승인했고 2조감독과 제작 PD가 남았다."
          :width="1128"
          :height="479"
        />
      </FeatureBlock>

      <FeatureBlock :title="['확정되면', '바로 알립니다']" desc="새 콜시트가 나가면 알림이 옵니다.">
        <AppFrame
          :src="bell"
          alt="알림 목록. 확정 콜시트 v2 배포 알림과 승인 결과 알림이 쌓여 있다."
          :width="362"
          :height="516"
          class="mx-auto w-full max-w-[362px]"
        />
      </FeatureBlock>
    </div>

    <section id="preview" class="border-t py-20 md:py-28">
      <div class="wrap flex flex-col gap-10">
        <div class="flex flex-col gap-3">
          <h2 class="section-title">우천 한 건이 처리되는 순서</h2>
          <p class="lede">실제 데모에서 찍은 화면입니다.</p>
        </div>
        <ProductWalkthrough />
      </div>
    </section>

    <FaqSection />

    <section id="start" class="border-t py-20 md:py-28">
      <div class="wrap flex flex-col items-start gap-8 md:flex-row md:items-end md:justify-between">
        <div class="flex flex-col gap-3">
          <h2 class="section-title">직접 해 보세요</h2>
          <p class="lede">데모 계정으로 처음부터 끝까지 해 볼 수 있습니다.</p>
        </div>
        <Button as-child size="lg" class="h-12 shrink-0 px-6 text-base">
          <RouterLink to="/login">데모 시작하기</RouterLink>
        </Button>
      </div>
    </section>
  </main>
  <SiteFooter />
</template>
