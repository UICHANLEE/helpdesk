<script setup lang="ts">
import type { TimelineEvent } from '../../types/incident'
defineProps<{ events: TimelineEvent[] }>()
const names: Record<string, string> = { user: 'USER', jev: 'JEV', retrieval: 'RAFT', tool_started: 'TOOL', tool_result: 'TOOL RESULT', reasoning_started: 'QWEN', reasoning: 'REASON', action: 'ACTION', status_changed: 'STATUS', error: 'ERROR' }
function summary(event: TimelineEvent): string {
  const data = event.data
  if (event.type === 'user') return String(data.message || '')
  if (event.type === 'jev') { const c = data.classification as Record<string, unknown> | undefined; return `${c?.domain || 'UNKNOWN'}${c?.secondary ? ` → ${c.secondary}` : ''} · ${c?.severity || ''} / ${c?.complexity || ''}` }
  if (event.type === 'retrieval') { const matches = data.matches as Array<{id:string;score?:number}> | undefined; return matches?.length ? matches.map(item => `${item.id}${item.score ? ` · 점수 ${item.score.toFixed(2)}` : ''}`).join(' · ') : '일치하는 과거 장애가 없습니다.' }
  if (event.type === 'tool_started') return `${data.tool} 실행 중`
  if (event.type === 'tool_result') { const result = data.result as Record<string, unknown> | undefined; return `${data.tool} · ${result?.summary || result?.status || ''}` }
  if (event.type === 'reasoning_started') return `${data.model} · ${data.complexity} 판단 진행 중`
  if (event.type === 'reasoning') return '진단 Trace와 원인 후보가 업데이트되었습니다.'
  if (event.type === 'action') return String(data.recommended_action || data.decision || '다음 조치 제안')
  if (event.type === 'status_changed') return data.status === 'resolved' ? '운영자가 Incident를 해결됨으로 표시했습니다.' : `상태 변경: ${data.status}`
  return String(data.message || '')
}
</script>
<template><div class="timeline"><article v-for="event in events" :key="event.id" class="timeline-event" :class="event.type"><div class="timeline-time">{{ new Date(event.created_at).toLocaleTimeString('ko-KR', { hour12:false }) }}</div><div class="timeline-node"></div><div class="timeline-body"><span class="event-label">{{ event.type === 'jev' && (event.data.classification as Record<string, unknown>)?.source === 'rules' ? 'RULES' : names[event.type] || event.type.toUpperCase() }}</span><p>{{ summary(event) }}</p></div></article><div v-if="!events.length" class="empty-state">진단 이벤트를 기다리는 중입니다.</div></div></template>
