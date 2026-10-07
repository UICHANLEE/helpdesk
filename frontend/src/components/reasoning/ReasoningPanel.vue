<script setup lang="ts">
import { computed, ref } from 'vue'
import type { IncidentState, TimelineEvent } from '../../types/incident'

const props = defineProps<{ state: IncidentState; events: TimelineEvent[] }>()
const tab = ref<'summary' | 'evidence' | 'reasoning' | 'raw'>('summary')
const relationNames: Record<string, string> = {
  reported: '사용자 보고', observed: '관찰한 결과', failed_check: '실패한 점검', historical_match: '유사 사례', follow_up_check: '추가 점검', operator_verification: '운영자 확인', example_scenario: '가상 해결 기록',
}
const toolResults = computed(() => props.events.filter(event => event.type === 'tool_result'))
const toolCount = (status: string) => toolResults.value.filter(event =>
  (event.data.result as Record<string, unknown> | undefined)?.status === status).length
function referencedEvent(id: number): TimelineEvent | undefined {
  return props.events.find(event => event.id === id)
}
function eventSummary(event: TimelineEvent | undefined): string {
  if (!event) return '이벤트를 찾을 수 없음'
  if (event.type === 'user') return String(event.data.message || '사용자 요청')
  if (event.type === 'tool_result') {
    const result = event.data.result as Record<string, unknown> | undefined
    return `${event.data.tool} · ${result?.summary || result?.status || '결과 없음'}`
  }
  if (event.type === 'retrieval') return `RAFT 유사 사례 ${((event.data.matches as unknown[]) || []).length}건`
  if (event.type === 'status_changed') return props.state.origin === 'example' ? '가상 시나리오의 원인과 조치 예시' : '운영자가 원인과 성공한 조치를 확인함'
  if (event.type === 'example_reviewed') return `가상 참고 답안: ${event.data.revised_cause || ''}`
  return event.type
}
function duration(event: TimelineEvent | undefined): string {
  const trace = event?.data.trace as Record<string, unknown> | undefined
  return typeof trace?.duration_ms === 'number' ? ` · ${trace.duration_ms}ms` : ''
}
</script>

<template>
  <aside class="inspector">
    <div class="inspector-tabs"><button v-for="item in ['summary', 'evidence', 'reasoning', 'raw'] as const" :key="item" :class="{ active: tab === item }" @click="tab = item">{{ item }}</button></div>
    <div v-if="tab === 'summary'" class="inspector-content">
      <div class="inspector-section"><small>CURRENT DIAGNOSIS</small><h3>{{ props.state.diagnosis || '조사 중' }}</h3><span class="confidence">{{ props.state.origin === 'example' ? '가상 시나리오 · 실제 검증 아님' : props.state.providerStatus.answer_source === 'verified_history_check' ? '유사 해결 기록 참고 · 현재 미검증' : props.state.classification?.source === 'jev' ? `Jev ${Math.round((props.state.classification.confidence || 0) * 100)}%` : '규칙 기반 초기 판단' }}</span></div>
      <div class="inspector-section"><small>EVIDENCE</small><p v-for="fact in props.state.confirmedFacts" :key="fact.id" class="evidence-line">✓ {{ fact.source }} · {{ fact.summary }}</p><p v-if="!props.state.confirmedFacts.length" class="soft-text">확인된 운영 도구 결과 없음</p></div>
      <div class="inspector-section"><small>HYPOTHESES</small><p v-for="hypothesis in props.state.hypotheses" :key="hypothesis.id">{{ hypothesis.name }}</p><p v-if="!props.state.hypotheses.length" class="soft-text">추가 근거를 기다리는 중</p></div>
      <div class="inspector-section"><small>NEXT ACTION</small><p>{{ props.state.recommendedAction }}</p></div>
    </div>
    <div v-else-if="tab === 'evidence'" class="inspector-content">
      <div class="inspector-section"><small>TRACE ID</small><p class="trace-id">{{ props.state.traceId || `TR-${props.state.id}` }}</p></div>
      <div class="inspector-section"><small>TOOL SIGNALS</small><p>정상 {{ toolCount('ok') }} · 실패 {{ toolCount('error') }} · 미연결 {{ toolCount('unconfigured') }}</p><p class="soft-text">아래 연결은 판단 시 참고한 기록이며, 미검증 진단의 원인을 확정하지 않습니다.</p></div>
      <div v-for="claim in props.state.claims || []" :key="claim.id" class="inspector-section"><small>{{ claim.verification === 'operator_verified' ? '운영자 확인' : claim.verification === 'example' ? '가상 예시' : '미검증 진단' }} · {{ claim.id }}</small><h3>{{ claim.text }}</h3><p v-if="!claim.references.length" class="soft-text">연결된 점검 근거가 없습니다.</p><a v-for="reference in claim.references" :key="reference.eventId" class="claim-reference" :href="`#event-${reference.eventId}`"><span>{{ relationNames[reference.relation] || reference.relation }}</span><strong>{{ eventSummary(referencedEvent(reference.eventId)) }}{{ duration(referencedEvent(reference.eventId)) }}</strong></a></div>
      <p v-if="!props.state.claims?.length" class="soft-text">새 진단부터 주장과 점검 이벤트의 연결이 표시됩니다.</p>
    </div>
    <div v-else-if="tab === 'reasoning'" class="inspector-content"><div v-for="(step, index) in props.state.reasoningTrace" :key="index" class="trace-step"><small>{{ step.step }}</small><p>{{ step.text }}</p><span v-if="index < props.state.reasoningTrace.length - 1">↓</span></div><p v-if="!props.state.reasoningTrace.length" class="soft-text">판단 근거를 정리하는 중입니다.</p></div>
    <div v-else class="inspector-content"><pre>{{ JSON.stringify(props.state, null, 2) }}</pre></div>
  </aside>
</template>
