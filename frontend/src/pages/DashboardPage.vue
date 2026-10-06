<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listIncidents } from '../services/incident'
import type { IncidentRecord } from '../types/incident'
import IncidentList from '../components/incident/IncidentList.vue'
const items = ref<IncidentRecord[]>([])
onMounted(async () => { try { items.value = await listIncidents() } catch { /* show empty */ } })
</script>
<template><div class="page-wrap"><div class="page-eyebrow">OPERATIONS OVERVIEW</div><div class="page-heading"><div><h1>Dashboard<span class="title-dot">.</span></h1><p>지금 확인할 Incident와 시스템 연결 상태를 한곳에서 봅니다.</p></div><RouterLink to="/diagnose" class="primary-button">Quick Diagnose →</RouterLink></div><div class="metric-grid"><div class="metric-card"><small>TOTAL INCIDENTS</small><strong>{{ items.length }}</strong></div><div class="metric-card"><small>ACTIVE</small><strong>{{ items.filter(item => item.state.status !== 'resolved').length }}</strong></div><div class="metric-card"><small>RESOLVED</small><strong>{{ items.filter(item => item.state.status === 'resolved').length }}</strong></div></div><div class="section-heading"><h2>Recent incidents</h2><RouterLink to="/incidents">View all →</RouterLink></div><div class="list-panel"><IncidentList :incidents="items.slice(0, 6)" /></div></div></template>
