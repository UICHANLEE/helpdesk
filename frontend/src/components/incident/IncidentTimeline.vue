<script setup lang="ts">
import type { TimelineEvent } from '../../types/incident'
defineProps<{ events: TimelineEvent[] }>()
const names: Record<string, string> = { user: 'USER', jev: 'JEV', retrieval: 'RAFT', tool_started: 'TOOL', tool_result: 'TOOL RESULT', reasoning_started: 'QWEN', reasoning: 'REASON', action: 'ACTION', status_changed: 'STATUS', error: 'ERROR', example_seeded: 'QUESTION', rehearsal_started: 'PRACTICE', rehearsal_interrupted: 'RETRY', example_reviewed: 'REVISION' }
function summary(event: TimelineEvent): string {
  const data = event.data
  if (event.type === 'user') return String(data.message || '')
  if (event.type === 'example_seeded') return '연습할 질문이 등록되었습니다. 진단은 아직 실행되지 않았습니다.'
  if (event.type === 'rehearsal_started') return '실제 진단 흐름을 시작했습니다. Jev, 검색, 연결된 도구와 Qwen 결과를 기다립니다.'
  if (event.type === 'rehearsal_interrupted') return '이전 진단이 중단되어 질문을 다시 실행합니다.'
  if (event.type === 'example_reviewed') return `첫 판단: ${data.first_diagnosis || '없음'} → 수정: ${data.revised_cause || ''}`
  if (event.type === 'jev') { const c = data.classification as Record<string, unknown> | undefined; return `${c?.domain || 'UNKNOWN'}${c?.secondary ? ` → ${c.secondary}` : ''} · ${c?.severity || ''} / ${c?.complexity || ''}` }
  if (event.type === 'retrieval') { const matches = data.matches as Array<{id:string;score?:number;verification?:string}> | undefined; const trace = data.trace as Record<string, unknown> | undefined; const timing = typeof trace?.duration_ms === 'number' ? ` · ${trace.duration_ms}ms` : ''; return (matches?.length ? matches.map(item => `${item.id} (${item.verification === 'verified' ? '확인됨' : item.verification === 'example' ? '예시' : '미검증'})${item.score ? ` · 점수 ${item.score.toFixed(2)}` : ''}`).join(' · ') : '일치하는 과거 장애가 없습니다.') + timing }
  if (event.type === 'tool_started') return `${data.tool} 실행 중`
  if (event.type === 'tool_result') { const result = data.result as Record<string, unknown> | undefined; const trace = data.trace as Record<string, unknown> | undefined; return `${data.tool} · ${result?.summary || result?.status || ''}${typeof trace?.duration_ms === 'number' ? ` · ${trace.duration_ms}ms` : ''}` }
  if (event.type === 'reasoning_started') return `${data.model} · ${data.complexity} 판단 진행 중`
  if (event.type === 'reasoning') return '진단 Trace와 원인 후보가 업데이트되었습니다.'
  if (event.type === 'action') return String(data.recommended_action || data.decision || '다음 조치 제안')
  if (event.type === 'status_changed') return data.origin === 'example' ? '이전 방식으로 입력한 가상 답안입니다. 새 연습 진단 기록과 구분하세요.' : data.status === 'resolved' ? '운영자가 Incident를 해결됨으로 표시했습니다.' : `상태 변경: ${data.status}`
  return String(data.message || '')
}
</script>
<template><div class="timeline"><article v-for="event in events" :id="`event-${event.id}`" :key="event.id" class="timeline-event" :class="event.type"><div class="timeline-time">{{ new Date(event.created_at).toLocaleTimeString('ko-KR', { hour12:false }) }}</div><div class="timeline-node"></div><div class="timeline-body"><span class="event-label">{{ event.type === 'jev' && (event.data.classification as Record<string, unknown>)?.source === 'rules' ? 'RULES' : names[event.type] || event.type.toUpperCase() }}</span><p>{{ summary(event) }}</p></div></article><div v-if="!events.length" class="empty-state">진단 이벤트를 기다리는 중입니다.</div></div></template>
