<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getKnowledge, publishFaq, type KnowledgeData, type FrequentError } from '../services/knowledge'

const data = ref<KnowledgeData | null>(null)
const selected = ref<FrequentError | null>(null)
const question = ref('')
const answer = ref('')
const message = ref('')
async function load() { try { data.value = await getKnowledge() } catch { message.value = 'FAQ 데이터를 불러오지 못했습니다.' } }
function select(item: FrequentError) { selected.value = item; question.value = `${item.diagnosis} 오류는 어떻게 확인하나요?`; answer.value = item.suggested_answer; message.value = '' }
async function save() {
  if (!selected.value) return
  try { await publishFaq({ incident_id: selected.value.example_incident_id, question: question.value, answer: answer.value }); message.value = 'FAQ를 게시했습니다.'; selected.value = null; await load() }
  catch (error) { message.value = error instanceof Error ? error.message : 'FAQ 게시 실패' }
}
onMounted(load)
</script>

<template>
  <div class="page-wrap">
    <div class="page-eyebrow">ERROR INTELLIGENCE</div>
    <div class="page-heading"><div><h1>FAQ Dashboard<span class="title-dot">.</span></h1><p>반복되는 오류를 확인하고 해결된 사례에서 FAQ를 만듭니다.</p></div><RouterLink to="/knowledge/raft" class="secondary-button">지식 검색 →</RouterLink></div>
    <div v-if="data" class="metric-grid"><div class="metric-card"><small>QUESTIONS</small><strong>{{ data.stats.questions }}</strong></div><div class="metric-card"><small>RESOLVED CASES</small><strong>{{ data.stats.resolved_knowledge }}</strong></div><div class="metric-card"><small>PUBLISHED FAQ</small><strong>{{ data.stats.faq_count }}</strong></div></div>
    <div class="section-heading"><h2>자주 발생한 오류</h2><small>진단명과 영역별 집계</small></div>
    <div class="list-panel"><div v-for="item in data?.frequent_errors" :key="item.signature" class="faq-row"><div><small>{{ item.domain }} · {{ item.latest_at.slice(0, 10) }}</small><strong>{{ item.diagnosis }}</strong><RouterLink :to="`/incidents/${item.example_incident_id}`">{{ item.example_incident_id }} →</RouterLink></div><span>{{ item.count }}건 <small>· 해결 {{ item.resolved }}</small></span><button class="secondary-button" :disabled="!item.resolved" @click="select(item)">{{ item.faq_published ? 'FAQ 수정' : 'FAQ 만들기' }}</button></div><div v-if="!data?.frequent_errors.length" class="empty-state">아직 집계할 진단 기록이 없습니다.</div></div>
    <form v-if="selected" class="faq-editor surface-card" @submit.prevent="save"><h2>FAQ 작성 · {{ selected.domain }}</h2><label>질문<input v-model="question" required maxlength="500" /></label><label>답변<textarea v-model="answer" required maxlength="4000" placeholder="확인된 해결 방법과 주의사항을 입력하세요." /></label><button class="primary-button">FAQ 게시</button></form>
    <p v-if="message" class="soft-text">{{ message }}</p>
    <div class="section-heading"><h2>게시된 FAQ</h2></div><div v-for="item in data?.faq" :key="item.id" class="knowledge-item"><p>{{ item.question }}</p><strong>{{ item.answer }}</strong></div>
  </div>
</template>
