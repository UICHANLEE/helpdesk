<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import IncidentList from '../components/incident/IncidentList.vue'
import { listIncidents } from '../services/incident'
import type { IncidentRecord } from '../types/incident'

const props = defineProps<{ status?: string }>()
const route = useRoute()
const items = ref<IncidentRecord[]>([])
const error = ref('')
const domain = ref('all')
const kind = ref('all')
const page = ref(1)
const pageSize = 50
const kindNames: Record<string, string> = {
  conversation: '대화 기반', general: '기존 일반', scenario: '상황별 문의',
  variation: '표현 변형', uncertain: '정보 부족',
}
const kindOrder = ['conversation', 'general', 'scenario', 'variation', 'uncertain']
const domains = computed(() => [...new Set(items.value.map(item => item.state.exampleReference?.domain).filter((value): value is string => !!value))].sort())
const filteredItems = computed(() => {
  const query = String(route.query.q || '').trim().toLowerCase()
  const matching = items.value.filter(item =>
    (!query || `${item.id} ${item.state.title || ''} ${item.message} ${item.state.diagnosis}`.toLowerCase().includes(query)) &&
    (props.status !== 'examples' || domain.value === 'all' || item.state.exampleReference?.domain === domain.value) &&
    (props.status !== 'examples' || kind.value === 'all' || item.state.exampleReference?.kind === kind.value))
  if (props.status === 'examples') matching.sort((a, b) =>
    kindOrder.indexOf(a.state.exampleReference?.kind || '') - kindOrder.indexOf(b.state.exampleReference?.kind || '') ||
    (a.state.seedKey || '').localeCompare(b.state.seedKey || ''))
  return matching
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize)))
const visibleItems = computed(() => filteredItems.value.slice((page.value - 1) * pageSize, page.value * pageSize))
async function refresh() {
  try { items.value = await listIncidents(props.status); error.value = '' }
  catch { error.value = 'Incident 목록을 불러오지 못했습니다.' }
}
onMounted(refresh)
watch(() => props.status, refresh)
watch([() => props.status, () => route.query.q, domain, kind], () => { page.value = 1 })
</script>
<template>
  <div class="page-wrap">
    <div class="page-eyebrow">OPERATIONS <span>·</span> INCIDENTS</div>
    <div class="page-heading"><div><h1>Incidents<span class="title-dot">.</span></h1><p>실제 장애 기록과 가상 연습 사례를 구분해 확인합니다.</p></div><RouterLink to="/incidents" class="primary-button">Open Board ↗</RouterLink></div>
    <div class="tab-links"><RouterLink to="/incidents">Board</RouterLink><RouterLink to="/incidents/list">Live list</RouterLink><RouterLink to="/incidents/active">Active</RouterLink><RouterLink to="/incidents/resolved">Resolved</RouterLink><RouterLink to="/incidents/examples">Examples</RouterLink></div>
    <p v-if="status === 'examples'" class="soft-text">질문을 열어 진단을 실행하고 첫 판단을 기다린 뒤, 참고 답안과 비교해 원인·조치를 수정하세요. 가상 사례는 실제 장애 해결 실적이나 RAFT 정답에 포함되지 않습니다.</p>
    <div v-if="status === 'examples'" class="example-filters"><label>영역<select v-model="domain"><option value="all">전체</option><option v-for="name in domains" :key="name" :value="name">{{ name }}</option></select></label><label>질문 유형<select v-model="kind"><option value="all">전체</option><option v-for="(name, key) in kindNames" :key="key" :value="key">{{ name }}</option></select></label><span>{{ filteredItems.length }} / {{ items.length }}건</span></div>
    <p v-if="route.query.q" class="search-caption">“{{ route.query.q }}” 검색 결과 {{ filteredItems.length }}건</p>
    <div class="list-panel"><IncidentList :incidents="visibleItems" /></div>
    <div v-if="filteredItems.length > pageSize" class="example-pagination"><button class="secondary-button" :disabled="page === 1" @click="page--">← 이전</button><span>{{ page }} / {{ pageCount }}</span><button class="secondary-button" :disabled="page === pageCount" @click="page++">다음 →</button></div>
    <p v-if="error" class="inline-error">{{ error }}</p>
  </div>
</template>
