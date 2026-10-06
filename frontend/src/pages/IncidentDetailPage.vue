<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import IncidentList from '../components/incident/IncidentList.vue'
import IncidentTimeline from '../components/incident/IncidentTimeline.vue'
import ReasoningPanel from '../components/reasoning/ReasoningPanel.vue'
import { incidentStore, loadIncident, refreshIncidents, applyEvent } from '../stores/incident'
import { watchIncident } from '../services/stream'
import { updateIncidentStatus } from '../services/incident'

const route = useRoute()
const error = ref('')
const showResolution = ref(false)
const rootCause = ref('')
const successfulAction = ref('')
const resolutionNote = ref('')
let source: EventSource | null = null
async function load(id: string) {
  source?.close()
  try { await Promise.all([loadIncident(id), refreshIncidents()]); if (incidentStore.current?.state.status === 'investigating') source = watchIncident(id, applyEvent) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Incident를 불러오지 못했습니다.' }
}
onMounted(() => load(String(route.params.incidentId)))
watch(() => route.params.incidentId, id => { if (id) load(String(id)) })
onUnmounted(() => source?.close())
async function resolveIncident() {
  const id = String(route.params.incidentId)
  try { await updateIncidentStatus(id, 'resolved', { root_cause: rootCause.value, successful_action: successfulAction.value, note: resolutionNote.value }); showResolution.value = false; await loadIncident(id); await refreshIncidents() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '상태를 변경하지 못했습니다.' }
}
</script>
<template><div class="workspace-page"><aside class="workspace-list"><div class="workspace-list-head"><span>INCIDENTS</span><RouterLink to="/diagnose">＋</RouterLink></div><IncidentList :incidents="incidentStore.items" :selected-id="String(route.params.incidentId)" /></aside><section class="workspace-main"><div class="workspace-title"><div><small>INVESTIGATION / {{ route.params.incidentId }}</small><h1>{{ incidentStore.current?.state.diagnosis || 'Incident Workspace' }}</h1></div><div class="workspace-title-actions"><span class="status-label">{{ incidentStore.current?.state.status }}</span><button v-if="incidentStore.current && incidentStore.current.state.status !== 'resolved'" class="secondary-button" @click="showResolution = !showResolution">해결 기록</button></div></div><form v-if="showResolution" class="resolution-form surface-card" @submit.prevent="resolveIncident"><h2>검증된 해결 기록</h2><p class="soft-text">확인된 원인과 실제 성공한 조치만 다음 진단의 검색 근거로 사용됩니다.</p><label>확인된 원인<input v-model="rootCause" required maxlength="1000" /></label><label>성공한 조치<input v-model="successfulAction" required maxlength="2000" /></label><label>추가 메모<textarea v-model="resolutionNote" maxlength="2000" /></label><button class="primary-button">해결 처리 및 지식 저장</button></form><div v-if="incidentStore.current" class="workspace-user"><span>USER INPUT</span><p>{{ incidentStore.current.message }}</p></div><div v-if="incidentStore.current?.state.resolution" class="knowledge-item"><span class="page-eyebrow">VERIFIED RESOLUTION</span><p>{{ incidentStore.current.state.resolution.rootCause }}</p><strong>{{ incidentStore.current.state.resolution.successfulAction }}</strong></div><div class="workspace-stream-heading">ACTIVITY STREAM <small>{{ incidentStore.events.length }} EVENTS</small></div><IncidentTimeline :events="incidentStore.events" /><p v-if="error" class="inline-error">{{ error }}</p></section><ReasoningPanel v-if="incidentStore.current" :state="incidentStore.current.state" /><aside v-else class="inspector"><div class="empty-state">Incident를 불러오는 중입니다.</div></aside></div></template>
