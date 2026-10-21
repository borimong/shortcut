<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleAlert } from '@lucide/vue'
import logoUrl from '../assets/logo.webp'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { useAuthStore } from '../stores/auth.js'
import { DEMO_ACCOUNTS } from '../labels.js'

// 시드 계정은 모두 같은 비밀번호라 빠른 선택에서 바로 채운다.
const DEMO_PASSWORD = 'shortcut1234'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref(null)
const busy = ref(false)

async function submit() {
  if (busy.value) return
  error.value = null
  busy.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/board'
    router.replace(redirect)
  } catch (e) {
    error.value = e.status === 401 ? { message: '아이디 또는 비밀번호가 올바르지 않습니다.', code: e.code } : e
  } finally {
    busy.value = false
  }
}

function quick(account) {
  username.value = account.username
  password.value = DEMO_PASSWORD
  submit()
}
</script>

<template>
  <div class="grid min-h-[calc(100vh-40px)] items-center gap-10 py-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
    <section class="flex flex-col gap-4">
      <RouterLink to="/" aria-label="소개 페이지로 이동"><img :src="logoUrl" alt="ShortCut" width="390" height="128" class="h-24 w-auto sm:h-32" /></RouterLink>
      <p class="text-lg text-muted-foreground">수많은 변수가 발생하는 바쁜 촬영현장, 최적의 콜시트를 바로 만들어드립니다</p>
    </section>

    <Card>
      <CardHeader>
        <CardTitle class="text-lg">로그인</CardTitle>
        <CardDescription>제작팀에서 받은 아이디와 비밀번호를 입력합니다.</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-col gap-6">
        <form @submit.prevent="submit">
          <FieldGroup>
            <Field>
              <FieldLabel for="username">아이디</FieldLabel>
              <Input id="username" v-model="username" autocomplete="username" required />
            </Field>
            <Field>
              <FieldLabel for="password">비밀번호</FieldLabel>
              <Input id="password" v-model="password" type="password" autocomplete="current-password" required />
            </Field>
            <Alert v-if="error" variant="destructive">
              <CircleAlert />
              <AlertDescription>{{ error.message }} <span class="mono">{{ error.code }}</span></AlertDescription>
            </Alert>
            <Button type="submit" :disabled="busy">
              <Spinner v-if="busy" data-icon="inline-start" />{{ busy ? '로그인 중' : '로그인' }}
            </Button>
          </FieldGroup>
        </form>

        <Separator />

        <div class="flex flex-col gap-3">
          <h2 class="text-sm font-medium">데모 계정으로 로그인</h2>
          <div class="grid grid-cols-2 gap-2">
            <Button
              v-for="a in DEMO_ACCOUNTS"
              :key="a.username"
              variant="outline"
              class="h-auto flex-col items-start gap-0.5 py-2 text-left whitespace-normal"
              :disabled="busy"
              @click="quick(a)"
            >
              <span>{{ a.name }}</span>
              <span class="text-xs font-normal text-muted-foreground">{{ a.title }}</span>
              <span class="mono text-[11px] font-normal text-muted-foreground">{{ a.role }}</span>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
