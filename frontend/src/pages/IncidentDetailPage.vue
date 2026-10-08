<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import IncidentList from '../components/incident/IncidentList.vue'
import IncidentTimeline from '../components/incident/IncidentTimeline.vue'
import ReasoningPanel from '../components/reasoning/ReasoningPanel.vue'
import { incidentStore, loadIncident, refreshIncidents, applyEvent } from '../stores/incident'
import { watchIncident } from '../services/stream'
import { rehearseExample, reviewExample, updateIncidentStatus } from '../services/incident'

const route = useRoute()
const error = ref('')
const showResolution = ref(false)
const rootCause = ref('')
const successfulAction = ref('')
const resolutionNote = ref('')
const runningExample = ref(false)
const sidebarItems = computed(() => {
  if (incidentStore.current?.state.origin !== 'example') return incidentStore.items
  const selected = String(route.params.incidentId)
  const index = incidentStore.items.findIndex(item => item.id === selected)
  if (index < 0) return incidentStore.items.slice(0, 60)
  const start = Math.max(0, index - 30)
  return incidentStore.items.slice(start, start + 60)
})
let source: EventSource | null = null
async function load(id: string) {
  source?.close()
  try { await loadIncident(id); await refreshIncidents(incidentStore.current?.state.origin === "example" ? "examples" : undefined); if (incidentStore.current?.state.status === 'investigating') source = watchIncident(id, applyEvent) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Incident를 불러오지 못했습니다.' }
}
onMounted(() => { showResolution.value = route.query.resolve === '1'; load(String(route.params.incidentId)) })
watch(() => route.params.incidentId, id => { if (id) load(String(id)) })
watch(() => route.query.resolve, value => { if (value === '1') showResolution.value = true })
onUnmounted(() => source?.close())
async function resolveIncident() {
  const id = String(route.params.incidentId)
  try { await updateIncidentStatus(id, 'resolved', { root_cause: rootCause.value, successful_action: successfulAction.value, note: resolutionNote.value }); showResolution.value = false; await loadIncident(id); await refreshIncidents() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '상태를 변경하지 못했습니다.' }
}
async function runExample() {
  const id = String(route.params.incidentId)
  runningExample.value = true; error.value = ''
  try { await rehearseExample(id); await load(id) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '연습 진단을 시작하지 못했습니다.' }
  finally { runningExample.value = false }
}
function toggleExampleResolution() {
  showResolution.value = !showResolution.value
  if (showResolution.value) {
    rootCause.value = incidentStore.current?.state.resolution?.rootCause || ''
    successfulAction.value = incidentStore.current?.state.resolution?.successfulAction || ''
    resolutionNote.value = incidentStore.current?.state.resolution?.note || ''
  }
}
function useReference() {
  const reference = incidentStore.current?.state.exampleReference
  if (!reference) return
  rootCause.value = reference.rootCause
  successfulAction.value = reference.successfulAction
}
async function saveExampleReview() {
  const id = String(route.params.incidentId)
  try { await reviewExample(id, { root_cause: rootCause.value, successful_action: successfulAction.value, note: resolutionNote.value }); showResolution.value = false; await loadIncident(id); await refreshIncidents('examples') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '예시 답안 수정에 실패했습니다.' }
}
</script>
<template><div class="workspace-page"><aside class="workspace-list"><div class="workspace-list-head"><RouterLink to="/incidents">← BOARD</RouterLink><RouterLink to="/diagnose">＋</RouterLink></div><IncidentList :incidents="sidebarItems" :selected-id="String(route.params.incidentId)" /></aside><section class="workspace-main"><div class="workspace-title"><div><small>INVESTIGATION / {{ route.params.incidentId }}</small><h1>{{ incidentStore.current?.state.origin === 'example' ? incidentStore.current.message : incidentStore.current?.message ? incidentStore.current.state.diagnosis || incidentStore.current.state.title : incidentStore.current?.state.title || 'Incident Workspace' }}</h1></div><div class="workspace-title-actions"><span class="status-label">{{ incidentStore.current?.state.examplePhase || incidentStore.current?.state.status }}</span><RouterLink v-if="incidentStore.current && !incidentStore.current.message && incidentStore.current.state.origin !== 'example'" :to="{ path: '/diagnose', query: { card: String(route.params.incidentId) } }" class="secondary-button">질문 입력 →</RouterLink><button v-if="incidentStore.current?.state.origin === 'example' && ['seeded','awaiting_review'].includes(incidentStore.current.state.examplePhase || '')" class="secondary-button" :disabled="runningExample" @click="runExample">{{ runningExample ? '시작 중…' : '질문 진단 실행' }}</button><button v-if="incidentStore.current?.state.origin === 'example' && ['awaiting_review','reviewed','preloaded'].includes(incidentStore.current.state.examplePhase || '')" class="secondary-button" @click="toggleExampleResolution">판단 수정</button><button v-if="incidentStore.current && incidentStore.current.state.origin !== 'example' && incidentStore.current.state.status !== 'resolved' && !!incidentStore.current.message" class="secondary-button" @click="showResolution = !showResolution">해결 기록</button></div></div><form v-if="showResolution && incidentStore.current?.state.origin !== 'example' && !!incidentStore.current?.message" class="resolution-form surface-card" @submit.prevent="resolveIncident"><h2>검증된 해결 기록</h2><p class="soft-text">확인된 원인과 실제 성공한 조치만 다음 진단의 해결 근거로 사용됩니다.</p><label>확인된 원인<input v-model="rootCause" required maxlength="1000" /></label><label>성공한 조치<input v-model="successfulAction" required maxlength="2000" /></label><label>추가 메모<textarea v-model="resolutionNote" maxlength="2000" /></label><button class="primary-button">해결 처리 및 지식 저장</button></form><div v-if="incidentStore.current?.state.origin === 'example'" class="knowledge-item"><span class="page-eyebrow">PRACTICE CASE · {{ incidentStore.current.state.examplePhase || 'seeded' }}</span><p>사전 작성한 가상 해결 사례입니다. 질문·상황·원인·조치가 저장되어 RAFT 검색에 사용됩니다. 실제 장애 해결 실적에는 포함되지 않으며, 판단 수정으로 내용을 고칠 수 있습니다.</p><p v-if="incidentStore.current.state.firstDiagnosis"><strong>첫 판단:</strong> {{ incidentStore.current.state.firstDiagnosis }}</p><p v-if="incidentStore.current.state.firstActions.length"><strong>첫 조치:</strong> {{ incidentStore.current.state.firstActions.join(' · ') }}</p><p v-if="incidentStore.current.state.examplePhase === 'investigating'">Jev → RAFT → 점검 도구 → Qwen 진단을 진행하고 있습니다…</p><p v-if="incidentStore.current.state.providerStatus.qwen === 'unavailable' && incidentStore.current.state.examplePhase === 'awaiting_review'">Qwen을 사용할 수 없어 규칙 기반 판단만 기록했습니다.</p></div><form v-if="showResolution && incidentStore.current?.state.origin === 'example'" class="resolution-form surface-card" @submit.prevent="saveExampleReview"><h2>예시 해결 기록 수정</h2><p class="soft-text">참고 답안은 가상의 정답 가정입니다. 실제 운영에서 확인한 사실로 표시되지 않습니다.</p><p v-if="incidentStore.current.state.exampleReference" class="soft-text">참고 원인: {{ incidentStore.current.state.exampleReference.rootCause }}<br />참고 조치: {{ incidentStore.current.state.exampleReference.successfulAction }}</p><button type="button" class="secondary-button" @click="useReference">참고 답안 입력</button><label>수정할 원인<input v-model="rootCause" required maxlength="1000" /></label><label>수정할 조치<input v-model="successfulAction" required maxlength="2000" /></label><label>수정 이유<textarea v-model="resolutionNote" maxlength="2000" /></label><button class="primary-button">수정 기록 및 RAFT 지식 저장</button></form><div v-if="incidentStore.current?.message" class="workspace-user"><span>USER INPUT</span><p>{{ incidentStore.current.message }}</p></div><div v-if="incidentStore.current?.state.resolution" class="knowledge-item"><span class="page-eyebrow">{{ incidentStore.current.state.origin === 'example' ? 'PREPARED RESOLUTION · 가상 해결 예시' : 'VERIFIED RESOLUTION' }}</span><p>{{ incidentStore.current.state.resolution.rootCause }}</p><strong>{{ incidentStore.current.state.resolution.successfulAction }}</strong></div><div class="workspace-stream-heading">ACTIVITY STREAM <small>{{ incidentStore.events.length }} EVENTS</small></div><IncidentTimeline :events="incidentStore.events" /><p v-if="error" class="inline-error">{{ error }}</p></section><ReasoningPanel v-if="incidentStore.current" :state="incidentStore.current.state" :events="incidentStore.events" /><aside v-else class="inspector"><div class="empty-state">Incident를 불러오는 중입니다.</div></aside></div></template>
