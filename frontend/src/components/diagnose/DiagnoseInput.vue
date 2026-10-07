<script setup lang="ts">
import { ref } from 'vue'
const emit = defineEmits<{ diagnose: [message: string] }>()
defineProps<{ busy?: boolean; disabled?: boolean }>()
const message = ref('')
const examples = [
  { label: 'DB 저장 실패', text: '문서 분석은 정상적으로 완료됐고 NAS에는 결과 파일이 있습니다. DB에는 데이터가 없습니다. POST /api/result/save HTTP 500.' },
  { label: 'Pod 연결 오류', text: 'kubectl에서 CrashLoopBackOff가 뜹니다. Pod 로그는 DB Connection refused입니다.' },
  { label: '인증 오류', text: '401 Unauthorized' },
]
function submit() { if (message.value.trim()) emit('diagnose', message.value.trim()) }
</script>
<template>
  <form class="diagnose-form" @submit.prevent="submit">
    <textarea v-model="message" :disabled="disabled || busy" maxlength="12000" placeholder="선택한 카드의 상황이나 로그를 입력하세요.&#10;&#10;예: NAS에는 파일이 있는데 DB에는 데이터가 없습니다. Save API가 HTTP 500을 반환합니다." aria-label="장애 상황 입력" />
    <div class="compose-footer"><div class="attach-controls"><button type="button" disabled title="MVP에서 준비 중">＋ Log</button><button type="button" disabled title="MVP에서 준비 중">＋ Screenshot</button><button type="button" disabled title="MVP에서 준비 중">＋ File</button></div><div class="compose-actions"><span>Jev → Qwen (연결 시)</span><button class="primary-button" type="submit" :disabled="disabled || busy || !message.trim()">{{ busy ? '분석 중…' : 'Diagnose →' }}</button></div></div>
  </form>
  <div class="examples"><span>EXAMPLES</span><button v-for="example in examples" :key="example.label" type="button" @click="message = example.text">{{ example.label }}</button></div>
</template>
