<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import DiagnoseInput from '../components/diagnose/DiagnoseInput.vue'
import DiagnoseResult from '../components/diagnose/DiagnoseResult.vue'
import IncidentTimeline from '../components/incident/IncidentTimeline.vue'
import { diagnose, getEvents, getState, listIncidents } from '../services/incident'
import { watchIncident } from '../services/stream'
import type { IncidentRecord, IncidentState, TimelineEvent } from '../types/incident'
import { executeTool, listTools } from '../services/tools'

const busy = ref(false)
const route = useRoute()
const error = ref('')
const cards = ref<IncidentRecord[]>([])
const selectedCardId = ref('')
const inputKey = ref(0)
const incidentId = ref('')
const state = ref<IncidentState | null>(null)
const events = ref<TimelineEvent[]>([])
const availableTools = ref<string[]>([])
const nextTool = computed(() => ({ DATABASE: 'db_health', KUBERNETES: 'get_pods', API: 'api_health', AUTH: 'token_check', LLM: 'llm_health', STORAGE: 'storage_health' } as Record<string, string>)[state.value?.classification?.domain || ''] || '')
let source: EventSource | null = null
let refreshTimer: ReturnType<typeof setTimeout> | null = null

async function loadCards() {
  try {
    cards.value = (await listIncidents('new')).filter(item => item.state.origin !== 'example' && !item.message.trim())
    const requested = String(route.query.card || '')
    selectedCardId.value = cards.value.some(item => item.id === requested) ? requested : cards.value[0]?.id || ''
  } catch { error.value = 'Todo 카드를 불러오지 못했습니다.' }
}
onMounted(loadCards)
watch(() => route.query.card, loadCards)

async function start(message: string) {
  if (!selectedCardId.value) { error.value = '먼저 보드에서 카드를 발행하세요.'; return }
  busy.value = true; error.value = ''; source?.close()
  try {
    const result = await diagnose(selectedCardId.value, message)
    incidentId.value = result.incident_id
    cards.value = cards.value.filter(card => card.id !== result.incident_id)
    selectedCardId.value = cards.value[0]?.id || ''
    inputKey.value += 1
    const [current, history] = await Promise.all([getState(result.incident_id), getEvents(result.incident_id)])
    state.value = current; events.value = history
    try { availableTools.value = (await listTools()).filter(item => item.configured).map(item => item.name) } catch { availableTools.value = [] }
    if (current.status === 'action_required' || current.status === 'resolved') { busy.value = false; return }
    source = watchIncident(result.incident_id, event => {
      if (!events.value.some(item => item.id === event.id)) events.value.push(event)
      if (refreshTimer) clearTimeout(refreshTimer)
      refreshTimer = setTimeout(async () => { try { state.value = await getState(result.incident_id) } catch { /* keep last state */ } refreshTimer = null }, 80)
      if (event.type === 'action' || event.type === 'error') { busy.value = false; source?.close() }
    }, () => { error.value = '실시간 연결이 끊어졌습니다. Incident 화면에서 기록을 다시 확인할 수 있습니다.'; busy.value = false })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '진단을 시작하지 못했습니다.'; busy.value = false }
}
async function runNextCheck() {
  if (!incidentId.value || !nextTool.value) return
  try { await executeTool(incidentId.value, nextTool.value); state.value = await getState(incidentId.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '도구 실행에 실패했습니다.' }
}
onUnmounted(() => { source?.close(); if (refreshTimer) clearTimeout(refreshTimer) })
</script>
<template><div class="page-wrap diagnose-page"><div class="page-eyebrow">INCIDENT INTELLIGENCE <span>·</span> QUICK DIAGNOSE</div><div class="page-heading"><div><h1>Quick Diagnose<span class="title-dot">.</span></h1><p>Todo 카드를 선택하고 장애 상황을 입력하세요. 제출하면 In Progress로 이동합니다.</p></div><RouterLink to="/incidents" class="secondary-button">Incident Board ↗</RouterLink></div><div class="diagnose-card-picker surface-card"><label>진단할 Todo 카드<select v-model="selectedCardId" :disabled="busy || !cards.length"><option v-for="card in cards" :key="card.id" :value="card.id">{{ card.id }} · {{ card.state.title || card.message }}</option></select></label><RouterLink to="/incidents" class="secondary-button">＋ 카드 발행</RouterLink></div><p v-if="!cards.length" class="soft-text">진단할 카드가 없습니다. Incident Board에서 카드를 먼저 발행하세요.</p><DiagnoseInput :key="inputKey" :busy="busy" :disabled="!selectedCardId" @diagnose="start" /><p v-if="error" class="inline-error">{{ error }}</p><div v-if="state" class="diagnose-results"><div class="results-top"><div><span class="section-eyebrow">LIVE INVESTIGATION</span><h2>{{ incidentId }}</h2></div><div class="result-buttons"><button type="button" class="secondary-button" :disabled="!availableTools.includes(nextTool)" :title="availableTools.includes(nextTool) ? `Run ${nextTool}` : '해당 점검 도구가 연결되지 않았습니다'" @click="runNextCheck">Run Next Check</button><RouterLink :to="`/incidents/${incidentId}`" class="secondary-button">Open Incident ↗</RouterLink></div></div><div class="flow-steps"><span v-for="step in ['observe','route','retrieve','reason','act','verify']" :key="step" :class="{ active: state.currentStep === step }">{{ step.toUpperCase() }}</span></div><DiagnoseResult :state="state" /><div class="diagnose-lower"><section class="surface-card"><div class="card-kicker">INVESTIGATION TIMELINE</div><IncidentTimeline :events="events" /></section><section class="surface-card"><div class="card-kicker">HISTORICAL MATCH</div><div v-for="match in state.raftMatches" :key="match.id" class="match-row"><strong>{{ match.id }}</strong><span>{{ match.title }}</span><small v-if="match.score">score {{ match.score.toFixed(2) }}</small></div><p v-if="!state.raftMatches.length" class="soft-text">일치하는 과거 장애가 없습니다.</p><div class="card-kicker evidence-kicker">EVIDENCE</div><div v-for="fact in state.confirmedFacts" :key="fact.id" class="evidence-line">✓ {{ fact.source }} · {{ fact.summary }}</div><p v-if="!state.confirmedFacts.length" class="soft-text">확인된 운영 도구 결과가 없습니다.</p></section></div></div></div></template>
