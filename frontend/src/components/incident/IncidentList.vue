<script setup lang="ts">
import type { IncidentRecord } from '../../types/incident'
import SeverityBadge from './SeverityBadge.vue'
defineProps<{ incidents: IncidentRecord[]; selectedId?: string }>()
</script>
<template><div class="incident-list"><RouterLink v-for="incident in incidents" :key="incident.id" :to="`/incidents/${incident.id}`" class="incident-list-item" :class="{ selected: selectedId === incident.id }"><div><strong>{{ incident.id }}</strong><span v-if="incident.state.origin === 'example'">{{ incident.state.examplePhase === 'reviewed' ? '연습 완료' : incident.state.examplePhase === 'awaiting_review' ? '수정 대기' : incident.state.examplePhase === 'investigating' ? '진단 중' : '질문 등록' }}</span><SeverityBadge :severity="incident.state.severity" /></div><p>{{ incident.state.title || incident.message }}</p><small>{{ new Date(incident.created_at).toLocaleString('ko-KR') }}</small></RouterLink><div v-if="!incidents.length" class="empty-state">저장된 Incident가 없습니다.</div></div></template>
