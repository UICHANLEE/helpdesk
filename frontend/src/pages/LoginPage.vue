<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const code = ref('')
const error = ref('')
const busy = ref(false)

async function login() {
  busy.value = true
  error.value = ''
  try {
    const response = await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code.value }) })
    if (!response.ok) {
      const body = await response.json()
      throw new Error(body.detail || '인증에 실패했습니다.')
    }
    await router.replace(typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/dashboard')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '인증에 실패했습니다.' }
  finally { busy.value = false; code.value = '' }
}
</script>
<template><main class="login-page"><div class="login-card"><div class="brand-icon">R</div><div class="page-eyebrow">RAFT INCIDENT INTELLIGENCE</div><h1>Helpdesk</h1><p>업무 기록과 진단 데이터에 접근하려면 인증번호를 입력하세요.</p><form @submit.prevent="login"><label for="access-code">인증번호</label><input id="access-code" v-model="code" type="password" autocomplete="one-time-code" required autofocus /><button class="primary-button" :disabled="busy">{{ busy ? '확인 중…' : '접속하기' }}</button></form><p v-if="error" class="inline-error" role="alert">{{ error }}</p></div></main></template>
