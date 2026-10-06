<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getKnowledge, type KnowledgeData } from '../services/knowledge'

const query = ref('')
const data = ref<KnowledgeData | null>(null)
const error = ref('')
async function load() {
  try { data.value = await getKnowledge(query.value); error.value = '' }
  catch { error.value = '지식 데이터를 불러오지 못했습니다.' }
}
onMounted(load)
</script>

<template>
  <div class="page-wrap">
    <div class="page-eyebrow">KNOWLEDGE BASE</div>
    <div class="page-heading"><div><h1>Knowledge<span class="title-dot">.</span></h1><p>해결된 사례와 공개된 FAQ를 다음 진단의 근거로 재사용합니다.</p></div><RouterLink to="/faq" class="secondary-button">FAQ 대시보드 →</RouterLink></div>
    <div v-if="data" class="metric-grid">
      <div class="metric-card"><small>RECORDED QUESTIONS</small><strong>{{ data.stats.questions }}</strong></div>
      <div class="metric-card"><small>RESOLVED KNOWLEDGE</small><strong>{{ data.stats.resolved_knowledge }}</strong></div>
      <div class="metric-card"><small>PUBLISHED FAQ</small><strong>{{ data.stats.faq_count }}</strong></div>
    </div>
    <p v-if="data" class="soft-text">로컬 RAG: {{ data.stats.vector.model }} 임베딩 {{ data.stats.vector.indexed }}건을 SQLite에 저장하고 BM25와 함께 검색합니다. 미해결 질문은 참고 사례로만 사용합니다. Ollama가 꺼져 있으면 키워드 검색으로 계속 작동합니다.</p>
    <form class="knowledge-search" @submit.prevent="load"><input v-model="query" placeholder="오류, 질문, 상황 검색" aria-label="지식 검색" /><button class="secondary-button">검색</button></form>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="data && query" class="knowledge-results">
      <div class="section-heading"><h2>검색 결과</h2><small>{{ data.results.length }}건</small></div>
      <div v-for="item in data.results" :key="item.id" class="knowledge-item"><div class="knowledge-item-top"><span>{{ item.type.toUpperCase() }} · {{ item.id }} · {{ item.status === 'verified' ? '확인됨' : '미해결 질문' }}</span><small>{{ item.retrieval === 'hybrid' ? '벡터 + 키워드' : '키워드' }} · 관련도 {{ item.score }}</small></div><p>{{ item.question }}</p><strong v-if="item.answer">{{ item.answer }}</strong><small v-else>확인된 해결책이 아직 없습니다.</small><ul v-if="item.actions.length"><li v-for="action in item.actions" :key="action">{{ action }}</li></ul><RouterLink v-if="item.type === 'incident'" :to="`/incidents/${item.id}`">원본 Incident →</RouterLink></div>
      <p v-if="!data.results.length" class="empty-state">일치하는 기록이 없습니다.</p>
    </div>
    <div v-if="data" class="section-heading"><h2>최근 공개 FAQ</h2><RouterLink to="/faq">전체 보기 →</RouterLink></div>
    <div v-for="item in data?.faq.slice(0, 5)" :key="item.id" class="knowledge-item"><span class="page-eyebrow">FAQ</span><p>{{ item.question }}</p><strong>{{ item.answer }}</strong></div>
    <p v-if="data && !data.faq.length" class="empty-state">아직 공개된 FAQ가 없습니다. 해결된 Incident에서 등록할 수 있습니다.</p>
  </div>
</template>
