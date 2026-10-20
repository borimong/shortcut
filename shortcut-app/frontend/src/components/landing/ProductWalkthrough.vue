<script setup>
import { computed, ref } from 'vue'
import { useDocumentVisibility, useIntersectionObserver, useMediaQuery, useRafFn } from '@vueuse/core'
import { Pause, Play } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import changeNew from '@/assets/screens/change-new.webp'
import taskTimeline from '@/assets/screens/task-timeline.webp'
import proposalDiff from '@/assets/screens/proposal-diff.webp'
import proposalApprovals from '@/assets/screens/proposal-approvals.webp'
import board from '@/assets/screens/board.webp'
import history from '@/assets/screens/history.webp'

// 실제 처리 순서대로 놓은 화면이다. fit은 액자 비율(1128:700)에 맞추는 방식이다.
const steps = [
  { title: '변경 접수', desc: '우천 소식을 적어 접수합니다', src: changeNew, w: 824, h: 550, fit: 'object-cover object-center', alt: '변경 입력 화면. 우천을 고르고 13시 이후 한강 공원 강수확률이 80%로 올랐다고 적었다.' },
  { title: '재계획', desc: '단계마다 무엇을 했는지 남깁니다', src: taskTimeline, w: 1128, h: 836, fit: 'object-cover object-top', alt: '재계획 진행 화면. 변경 감지부터 공지까지 열 단계와 도구 호출 기록이 보인다.' },
  { title: '변경안 검토', desc: '바뀐 것만 나란히 비교합니다', src: proposalDiff, w: 1128, h: 669, fit: 'object-contain object-top', alt: '변경안 화면. 장소, 장비, 시간대, 비용이 현재 일정과 어떻게 달라지는지 표로 보여 준다.' },
  { title: '승인', desc: '관련된 사람에게만 받습니다', src: proposalApprovals, w: 1128, h: 479, fit: 'object-contain object-top', alt: '승인 현황 화면. 여섯 명 중 네 명이 승인했고 두 명이 남았다.' },
  { title: '콜시트 발송', desc: '확정되면 바로 다시 나갑니다', src: board, w: 1128, h: 684, fit: 'object-contain object-top', alt: '오늘의 촬영판 화면. 확정 콜시트 v2 기준으로 콜타임과 팀별 콜타임, 종료 예정 시각이 보인다.' },
  { title: '이력 확인', desc: '거절부터 배포까지 기록됩니다', src: history, w: 664, h: 832, fit: 'object-cover object-top', alt: '변동 이력 화면. 동시녹음팀장 거절, 재계획, 새 변경안, 승인, 확정, 배포가 시간순으로 이어진다.' },
]

const DURATION = 3500

const root = ref(null)
const current = ref(0)
const elapsed = ref(0)
const hovering = ref(false)
const focused = ref(false)
const userPaused = ref(false)
const inView = ref(false)

const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')
const visibility = useDocumentVisibility()
useIntersectionObserver(root, ([entry]) => { inView.value = entry?.isIntersecting ?? false }, { threshold: 0.25 })

const autoplay = computed(() => !reducedMotion.value && !userPaused.value)
const running = computed(() => autoplay.value && !hovering.value && !focused.value && inView.value && visibility.value === 'visible')
const progress = computed(() => Math.min(elapsed.value / DURATION, 1))

function go(i) {
  current.value = (i + steps.length) % steps.length
  elapsed.value = 0
}

useRafFn(({ delta }) => {
  if (!running.value) return
  elapsed.value += delta
  if (elapsed.value >= DURATION) go(current.value + 1)
})

function onFocusOut(e) {
  if (!root.value?.contains(e.relatedTarget)) focused.value = false
}
</script>

<template>
  <div
    ref="root"
    class="grid items-start gap-8 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)] lg:gap-12"
    role="group"
    aria-roledescription="화면 넘김"
    aria-label="ShortCut 처리 순서"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
    @focusin="focused = true"
    @focusout="onFocusOut"
  >
    <Card class="min-w-0 gap-0 overflow-hidden rounded-md py-0 shadow-frame ring-0 lg:order-2">
      <div class="flex items-center gap-1.5 border-b px-3.5 py-2.5">
        <span class="size-2 rounded-full bg-border" aria-hidden="true" />
        <span class="size-2 rounded-full bg-border" aria-hidden="true" />
        <span class="size-2 rounded-full bg-border" aria-hidden="true" />
        <p class="ml-2 min-w-0 truncate text-[13px] text-muted-foreground" :aria-live="running ? 'off' : 'polite'">
          {{ current + 1 }}/{{ steps.length }} {{ steps[current].title }}
        </p>
        <Button
          v-if="!reducedMotion"
          type="button"
          variant="ghost"
          size="sm"
          class="ml-auto h-7 gap-1.5 px-2 text-[13px] text-muted-foreground"
          :aria-label="userPaused ? '자동 넘김 다시 켜기' : '자동 넘김 멈추기'"
          @click="userPaused = !userPaused"
        >
          <component :is="userPaused ? Play : Pause" class="size-3.5" aria-hidden="true" />
          {{ userPaused ? '재생' : '멈춤' }}
        </Button>
      </div>
      <div class="relative aspect-[1128/700] bg-card">
        <img
          v-for="(s, i) in steps"
          :key="s.src"
          :src="s.src"
          :alt="s.alt"
          :width="s.w"
          :height="s.h"
          loading="lazy"
          decoding="async"
          :aria-hidden="i !== current"
          :class="cn('absolute inset-0 size-full transition-opacity duration-700 ease-out', s.fit, i === current ? 'opacity-100' : 'opacity-0')"
        />
      </div>
    </Card>

    <ol class="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:order-1 lg:grid-cols-1">
      <li v-for="(s, i) in steps" :key="s.title">
        <button
          type="button"
          :aria-current="i === current ? 'step' : undefined"
          :aria-label="`${i + 1}단계 ${s.title} 화면 보기`"
          :class="cn(
            'flex w-full flex-col gap-1 rounded-md px-3 py-2.5 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            i === current ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          )"
          @click="go(i)"
        >
          <span class="flex items-baseline gap-2.5">
            <span class="mono text-[13px]">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="text-[16px] font-semibold">{{ s.title }}</span>
          </span>
          <span class="hidden pl-[34px] text-[14px] leading-snug lg:block">{{ s.desc }}</span>
          <span class="mt-1 block h-0.5 w-full overflow-hidden rounded-full bg-border" aria-hidden="true">
            <span
              class="block h-full origin-left bg-foreground"
              :style="{ transform: `scaleX(${i === current ? (autoplay ? progress : 1) : i < current ? 1 : 0})` }"
            />
          </span>
        </button>
      </li>
    </ol>
  </div>
</template>
