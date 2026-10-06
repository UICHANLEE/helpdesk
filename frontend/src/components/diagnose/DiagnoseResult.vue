<script setup lang="ts">
import type { IncidentState } from '../../types/incident'
import SeverityBadge from '../incident/SeverityBadge.vue'
defineProps<{ state: IncidentState }>()
</script>
<template>
  <section class="diagnosis-card"><div class="card-kicker"><span>DIAGNOSIS</span><span class="soft-text">{{ state.classification?.source === 'jev' ? 'Jev classification' : 'Rule fallback' }}</span></div><div class="diagnosis-title-row"><h2>{{ state.diagnosis || '조사 중입니다' }}</h2><SeverityBadge :severity="state.severity" /></div><div class="class-line"><span>{{ state.classification?.domain }}</span><span v-if="state.classification?.secondary">→ {{ state.classification.secondary }}</span><span class="complexity">{{ state.classification?.complexity }}</span></div><div class="actions-heading">Immediate Actions</div><ol class="action-list"><li v-for="action in state.immediateActions" :key="action">{{ action }}</li></ol><div class="next-action"><span>NEXT ACTION</span><strong>{{ state.recommendedAction || '근거 수집 중' }}</strong></div></section>
</template>
