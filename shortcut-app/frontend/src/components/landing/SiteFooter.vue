<script setup>
import logoUrl from '@/assets/logo.png'
import { Separator } from '@/components/ui/separator'

const cols = [
  { title: '서비스', links: ['작동 순서', '기능', '미리 보기', '자주 묻는 질문'] },
  { title: '기능', links: ['특보 감지', '일정 재조정', '승인 관리', '콜시트 배포'] },
  { title: '프로젝트', links: ['SKALA AI Agent 캡스톤', '기획 문서', '팀 소개'] },
]
</script>

<template>
  <footer class="dark bg-background pt-16 pb-10 text-muted-foreground">
    <div class="wrap">
      <a href="#top" class="flex justify-center" aria-label="ShortCut 처음으로"><img :src="logoUrl" alt="ShortCut" class="h-7 w-auto invert" /></a>
      <div class="mx-auto mt-12 grid max-w-[900px] grid-cols-2 gap-8 sm:grid-cols-3">
        <div v-for="c in cols" :key="c.title">
          <p class="mb-3.5 text-[13px] font-bold text-foreground">{{ c.title }}</p>
          <ul class="flex flex-col gap-2.5">
            <li v-for="l in c.links" :key="l"><a href="#top" class="text-[13px] hover:text-foreground">{{ l }}</a></li>
          </ul>
        </div>
      </div>
      <Separator class="mt-12" />
      <div class="mt-6 flex flex-col items-center gap-1 text-center text-xs">
        <p>© 2026 ShortCut</p>
        <p>캡스톤 프로젝트 데모입니다. 화면 속 작품, 인물, 일정은 모두 가상입니다.</p>
      </div>
    </div>
  </footer>
</template>
