<script setup>
import logoUrl from '@/assets/logo.webp'
import { Button } from '@/components/ui/button'
import { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList } from '@/components/ui/navigation-menu'

const links = [
  { href: '#features', label: '기능' },
  { href: '#preview', label: '미리 보기' },
  { href: '#faq', label: '자주 묻는 질문' },
]
</script>

<template>
  <header class="sticky top-0 z-20 border-b bg-background">
    <div class="flex h-16 items-center gap-7 px-5">
      <a href="#top" aria-label="ShortCut 처음으로"><img :src="logoUrl" alt="ShortCut" width="122" height="40" class="h-10 w-auto" /></a>
      <NavigationMenu class="ml-auto hidden md:flex">
        <NavigationMenuList>
          <NavigationMenuItem v-for="l in links" :key="l.href">
            <NavigationMenuLink :href="l.href" class="px-3 text-sm">{{ l.label }}</NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
      <div class="ml-auto flex items-center gap-2 md:ml-0">
        <Button as-child variant="ghost" size="sm" class="hidden md:inline-flex"><RouterLink to="/login">로그인</RouterLink></Button>
        <Button as-child variant="brand" size="sm"><RouterLink to="/login">데모 체험하기</RouterLink></Button>
      </div>
    </div>
  </header>
</template>
