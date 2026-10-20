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
      <FeatureBlock :title="['몇 줄로 끝나는', '변경 접수']" desc="변경 유형을 고르고 상황을 적어 주세요.">
        <AppFrame
          :src="changeNew"
          alt="변경 입력 화면. 우천을 고르고 상세 내용에 강수확률이 80%로 올랐다고 적었다."
          :width="824"
          :height="550"
        />
      </FeatureBlock>

      <FeatureBlock :title="['단계별로 보이는', '재계획 과정']" desc="계약, 주 52시간, 촬영 허가, 예산을 어떻게 확인했는지 단계마다 남깁니다." reverse>
        <AppFrame
          :src="taskTimeline"
          alt="재계획 진행 화면. 변경 감지부터 공지까지 열 단계를 마쳤고 오른쪽에 도구 호출 기록이 있다."
          :width="1128"
          :height="836"
        />
      </FeatureBlock>

      <FeatureBlock :title="['승인 요청 전', '자체 점검']" desc="변경안마다 근거와 위험을 100점 만점으로 보여 줍니다.">
        <AppFrame
          :src="proposalReview"
          alt="자체 검토 화면. 76점을 받았고 실행 위험, 하드 제약 근거 같은 항목별 점수가 막대로 나온다."
          :width="1128"
          :height="372"
        />
      </FeatureBlock>

      <FeatureBlock :title="['필요한 팀장만', '거치는 승인']" desc="누가 승인했고 누가 남았는지 바로 보입니다." reverse>
        <AppFrame
          :src="proposalApprovals"
          alt="승인 현황 화면. 연출감독, 1조감독, 동시녹음팀장, 촬영감독이 승인했고 2조감독과 제작 PD가 남았다."
          :width="1128"
          :height="479"
        />
      </FeatureBlock>

      <FeatureBlock :title="['확정 즉시', '새 콜시트 발송']" desc="새 콜시트가 나가면 알림으로 알려 드립니다.">
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
          <h2 class="section-title">우천 접수부터 콜시트 재발송까지</h2>
          <p class="lede">실제 데모 화면으로 보여 드립니다.</p>
        </div>
        <ProductWalkthrough />
      </div>
    </section>

    <FaqSection />

    <section id="start" class="border-t py-20 md:py-28">
      <div class="wrap flex flex-col items-start gap-8 md:flex-row md:items-end md:justify-between">
        <div class="flex flex-col gap-3">
          <h2 class="section-title">데모 계정으로 직접 써 보세요</h2>
          <p class="lede">접수부터 콜시트 발송까지 처음부터 끝까지 해 볼 수 있습니다.</p>
        </div>
        <Button as-child size="lg" class="h-12 shrink-0 px-6 text-base">
          <RouterLink to="/login">데모 체험하기</RouterLink>
        </Button>
      </div>
    </section>
  </main>
  <SiteFooter />
</template>
