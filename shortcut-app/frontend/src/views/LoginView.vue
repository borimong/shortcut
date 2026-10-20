<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import logoUrl from '../assets/logo.png'
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
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
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
  <div class="login">
    <section class="intro">
      <img :src="logoUrl" alt="ShortCut" class="logo" />
      <h1>촬영 변수가 생겨도<br />오늘 콜시트를 다시 짭니다</h1>
      <p class="muted">
        변경을 입력하면 Agent가 영향 범위와 규정 근거를 찾아 1/2/3안을 다시 조합하고, 필수 승인자가 모두 승인하면 콜시트를 확정해 배포합니다.
      </p>
    </section>

    <section class="card panel">
      <h2 class="card-title">로그인</h2>
      <form class="stack" @submit.prevent="submit">
        <label class="field">
          <span class="field-label">아이디</span>
          <input v-model="username" class="input" autocomplete="username" required />
        </label>
        <label class="field">
          <span class="field-label">비밀번호</span>
          <input v-model="password" class="input" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" class="inline-error">{{ error.message }} <span class="mono">{{ error.code }}</span></p>
        <button type="submit" class="btn btn-primary" :disabled="busy">{{ busy ? '로그인 중' : '로그인' }}</button>
      </form>

      <div class="demo">
        <p class="eyebrow">데모 계정 빠른 선택</p>
        <div class="demo-grid">
          <button
            v-for="a in DEMO_ACCOUNTS"
            :key="a.username"
            type="button"
            class="demo-btn"
            :disabled="busy"
            @click="quick(a)"
          >
            <strong>{{ a.name }}</strong>
            <span>{{ a.title }}</span>
            <span class="mono role">{{ a.role }}</span>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 480px);
  align-items: center;
  gap: 48px;
  padding: 48px 0;
}

.logo {
  height: 40px;
  width: auto;
  margin-bottom: 28px;
}

.intro h1 {
  font-size: 36px;
  line-height: 1.3;
  font-weight: 800;
  letter-spacing: -0.03em;
  margin-bottom: 16px;
}

.intro p {
  max-width: 460px;
}

.panel {
  padding: 32px;
}

.demo {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.demo-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.demo-btn {
  text-align: left;
  border: 1.5px solid var(--line);
  border-radius: 12px;
  background: #fff;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.demo-btn:hover:not(:disabled) {
  border-color: var(--charcoal);
  background: var(--head-bg);
}

.demo-btn span {
  font-size: 12.5px;
  color: var(--text-sub);
}

.demo-btn .role {
  font-size: 11px;
  color: var(--text-faint);
}

@media (max-width: 900px) {
  .login {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
    padding: 32px 0;
    min-height: auto;
  }

  .intro h1 {
    font-size: 26px;
  }
}

@media (max-width: 480px) {
  .panel {
    padding: 20px;
  }
}
</style>
