<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getKnowledge, getRaftDatasetStatus, type KnowledgeData, type RaftDatasetStatus } from '../services/knowledge'

const query = ref('')
const data = ref<KnowledgeData | null>(null)
const raftStatus = ref<RaftDatasetStatus | null>(null)
const error = ref('')
async function load() {
  try { data.value = await getKnowledge(query.value); error.value = '' }
  catch { error.value = '지식 데이터를 불러오지 못했습니다.' }
}
onMounted(() => { load(); getRaftDatasetStatus().then(value => { raftStatus.value = value }).catch(() => { /* Search remains available. */ }) })
</script>

<template>
  <div class="page-wrap">
    <div class="page-eyebrow">KNOWLEDGE BASE</div>
    <div class="page-heading"><div><h1>Knowledge<span class="title-dot">.</span></h1><p>실제 해결 기록과 예시 시나리오를 구분해 검색합니다.</p></div><RouterLink to="/faq" class="secondary-button">FAQ 대시보드 →</RouterLink></div>
    <div v-if="data" class="metric-grid">
      <div class="metric-card"><small>RECORDED QUESTIONS</small><strong>{{ data.stats.questions }}</strong></div>
      <div class="metric-card"><small>RESOLVED KNOWLEDGE</small><strong>{{ data.stats.resolved_knowledge }}</strong></div>
      <div class="metric-card"><small>PREPARED / REVIEWED</small><strong>{{ data.stats.example_preloaded }} / {{ data.stats.example_reviewed }}</strong></div>
      <div class="metric-card"><small>PUBLISHED FAQ</small><strong>{{ data.stats.faq_count }}</strong></div>
      <div class="metric-card"><small>TRAINED CASE MEMORY</small><strong>{{ data.stats.bootstrap.patterns }} 패턴</strong></div>
    </div>
    <p v-if="data" class="soft-text">로컬 RAG: {{ data.stats.vector.model }} 임베딩 {{ data.stats.vector.indexed }}건을 SQLite에 저장하고 BM25와 함께 검색합니다. 가상 패턴 {{ data.stats.bootstrap.patterns }}건은 {{ data.stats.bootstrap.question_variants }}개 질문 표현으로 찾아볼 수 있는 초기 지식이며 실제 장애 검증이나 Qwen 가중치 학습 결과는 아닙니다. Ollama가 꺼져 있으면 키워드 검색으로 계속 작동합니다.</p>
    <section v-if="raftStatus" class="raft-dataset-panel surface-card">
      <div><span class="page-eyebrow">RAFT · TRAINING DATA</span><h2>실제 해결 {{ raftStatus.verified_cases }}건 · 가상 해결 {{ raftStatus.synthetic_cases }}건</h2><p>질문·상황·원인·조치가 완성된 가상 사례를 RAFT 검색과 학습 데이터 후보에 사용합니다. 가상 원인과 조치는 실제 운영 검증과 구분하며, 근거가 없는 입력은 답변을 유보합니다. Qwen 가중치는 아직 변경되지 않았습니다. 학습 후보 {{ raftStatus.training_examples }}건.</p><small>Train {{ raftStatus.train_examples }} · Validation {{ raftStatus.validation_examples }} · {{ raftStatus.ready_for_fine_tuning ? '실제 사례 학습 검토 가능' : '실제 사례 추가 수집 필요' }}</small></div>
      <a class="secondary-button" href="/api/v1/knowledge/raft/dataset" download="helpdesk-raft-v1.jsonl" :aria-disabled="raftStatus.training_examples === 0" @click="raftStatus.training_examples === 0 && $event.preventDefault()">학습 데이터 내려받기 ↓</a>
    </section>
    <form class="knowledge-search" @submit.prevent="load"><input v-model="query" placeholder="오류, 질문, 상황 검색" aria-label="지식 검색" /><button class="secondary-button">검색</button></form>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="data && query" class="knowledge-results">
      <div class="section-heading"><h2>검색 결과</h2><small>{{ data.results.length }}건</small></div>
      <div v-for="item in data.results" :key="item.id" class="knowledge-item"><div class="knowledge-item-top"><span>{{ item.type.toUpperCase() }} · {{ item.id }} · {{ item.status === 'verified' ? '확인됨' : item.status === 'example' ? '가상 예시' : item.status === 'synthetic' ? '학습된 가상 패턴' : '미해결 질문' }}</span><small>{{ item.retrieval === 'hybrid' ? '벡터 + 키워드' : '키워드' }} · 관련도 {{ item.score }}</small></div><p>{{ item.question }}</p><strong v-if="item.answer">{{ item.answer }}</strong><small v-else>확인된 해결책이 아직 없습니다.</small><ul v-if="item.actions.length"><li v-for="action in item.actions" :key="action">{{ action }}</li></ul><RouterLink v-if="item.type === 'incident'" :to="`/incidents/${item.id}`">원본 Incident →</RouterLink></div>
      <p v-if="!data.results.length" class="empty-state">일치하는 기록이 없습니다.</p>
    </div>
    <div v-if="data" class="section-heading"><h2>최근 공개 FAQ</h2><RouterLink to="/faq">전체 보기 →</RouterLink></div>
    <div v-for="item in data?.faq.slice(0, 5)" :key="item.id" class="knowledge-item"><span class="page-eyebrow">FAQ</span><p>{{ item.question }}</p><strong>{{ item.answer }}</strong></div>
    <p v-if="data && !data.faq.length" class="empty-state">아직 공개된 FAQ가 없습니다. 해결된 Incident에서 등록할 수 있습니다.</p>
  </div>
</template>
