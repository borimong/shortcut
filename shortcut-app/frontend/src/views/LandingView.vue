<script setup>
import SiteNav from '@/components/landing/SiteNav.vue'
import HeroSection from '@/components/landing/HeroSection.vue'
import ExploreCards from '@/components/landing/ExploreCards.vue'
import FeatureBlock from '@/components/landing/FeatureBlock.vue'
import AppFrame from '@/components/landing/AppFrame.vue'
import AlertToast from '@/components/landing/AlertToast.vue'
import BellPanel from '@/components/landing/BellPanel.vue'
import Stripboard from '@/components/landing/Stripboard.vue'
import PlanDiff from '@/components/landing/PlanDiff.vue'
import ApprovalBoard from '@/components/landing/ApprovalBoard.vue'
import CallsheetTracker from '@/components/landing/CallsheetTracker.vue'
import MoreFeatures from '@/components/landing/MoreFeatures.vue'
import ProductShot from '@/components/landing/ProductShot.vue'
import FaqSection from '@/components/landing/FaqSection.vue'
import DeptSolutions from '@/components/landing/DeptSolutions.vue'
import SiteFooter from '@/components/landing/SiteFooter.vue'
import { Button } from '@/components/ui/button'
</script>

<template>
  <SiteNav />
  <main>
    <HeroSection />
    <ExploreCards />

    <div id="features" class="wrap grid gap-24 border-t py-22 md:gap-40 md:py-36">
      <FeatureBlock title="특보가 뜨면 영향받는 씬부터 찾습니다">
        <template #text>
          <p>촬영 장소마다 해당 특보 구역을 확인합니다. 특보가 뜨면 영향받는 씬과 출연 배우, 장비를 정리해 알림으로 보냅니다.</p>
        </template>
        <AppFrame>
          <div class="flex flex-col gap-3.5"><AlertToast /><BellPanel /></div>
        </AppFrame>
      </FeatureBlock>

      <FeatureBlock title="계약과 52시간을 어기는 안은 올리지 않습니다" reverse>
        <template #text>
          <p>새 일정안은 배우 계약 조건과 스태프 주 52시간, 촬영 허가 기간, 회차 예산 한도를 모두 통과해야 합니다.</p>
          <p>조건을 다 지킨 안 하나만 승인 요청으로 올라갑니다.</p>
        </template>
        <AppFrame action="승인 요청"><Stripboard /></AppFrame>
      </FeatureBlock>

      <FeatureBlock title="무엇이 왜 바뀌었는지 씬마다 보입니다">
        <template #text>
          <p>원본과 새 안을 씬 단위로 나란히 놓고, 바뀐 씬에는 근거가 된 계약 조항과 규정을 붙입니다.</p>
          <p>아직 회신이 없는 배우 일정은 미확정으로 남겨 둡니다.</p>
        </template>
        <AppFrame><PlanDiff /></AppFrame>
      </FeatureBlock>

      <FeatureBlock title="관련된 사람에게만 승인을 받습니다" reverse>
        <template #text>
          <p>장소가 바뀌면 연출감독과 동시녹음팀장에게, 추가 비용이 생기면 제작 PD에게 요청이 갑니다.</p>
          <p>누군가 거절하면 그 사유를 조건에 넣어 다음 안을 다시 짭니다.</p>
        </template>
        <AppFrame><ApprovalBoard /></AppFrame>
      </FeatureBlock>

      <FeatureBlock title="콜시트를 누가 확인했는지 알 수 있습니다">
        <template #text>
          <p>모두 승인하면 확정된 콜시트를 문자와 메일로 다시 보냅니다. 반송된 사람과 아직 열어 보지 않은 사람이 바로 보입니다.</p>
        </template>
        <AppFrame action="다시 보내기"><CallsheetTracker /></AppFrame>
      </FeatureBlock>
    </div>

    <MoreFeatures />

    <section id="preview" class="border-t py-20 md:py-28">
      <div class="wrap flex flex-col gap-10">
        <div class="flex flex-col gap-3">
          <h2 class="section-title">변경안을 검토하는 화면</h2>
          <p class="lede max-w-[44ch]">스트립보드에서 바뀐 씬을 보고, 오른쪽에서 누가 승인했는지 확인합니다.</p>
        </div>
        <ProductShot />
      </div>
    </section>

    <FaqSection />
    <DeptSolutions />

    <section id="start" class="border-t py-20 md:py-28">
      <div class="wrap flex flex-col items-start gap-8 md:flex-row md:items-end md:justify-between">
        <div class="flex flex-col gap-3">
          <h2 class="section-title">7화 촬영 전날 밤을 직접 겪어 보세요</h2>
          <p class="lede max-w-[46ch]">호우주의보가 뜬 순간부터 콜시트를 다시 보내기까지, 데모 데이터로 처음부터 끝까지 진행해 볼 수 있습니다.</p>
        </div>
        <Button as-child size="lg" class="h-12 shrink-0 px-6 text-base">
          <RouterLink to="/login">데모 시작하기</RouterLink>
        </Button>
      </div>
    </section>
  </main>
  <SiteFooter />
</template>
