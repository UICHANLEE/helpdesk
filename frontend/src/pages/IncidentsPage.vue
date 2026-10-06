<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import IncidentList from '../components/incident/IncidentList.vue'
import { listIncidents } from '../services/incident'
import type { IncidentRecord } from '../types/incident'
const props = defineProps<{ status?: string }>()
const route = useRoute()
const items = ref<IncidentRecord[]>([])
const filteredItems = computed(() => { const query = String(route.query.q || '').toLowerCase(); return query ? items.value.filter(item => `${item.id} ${item.message} ${item.state.diagnosis}`.toLowerCase().includes(query)) : items.value })
const error = ref('')
async function refresh() { try { items.value = await listIncidents(props.status) } catch { error.value = 'Incident 목록을 불러오지 못했습니다.' } }
onMounted(refresh)
watch(() => props.status, refresh)
</script>
<template><div class="page-wrap"><div class="page-eyebrow">OPERATIONS <span>·</span> INCIDENTS</div><div class="page-heading"><div><h1>Incidents<span class="title-dot">.</span></h1><p>저장된 장애와 진행 상태를 확인합니다.</p></div><RouterLink to="/diagnose" class="primary-button">＋ New diagnosis</RouterLink></div><div class="tab-links"><RouterLink to="/incidents">All</RouterLink><RouterLink to="/incidents/active">Active</RouterLink><RouterLink to="/incidents/resolved">Resolved</RouterLink></div><p v-if="route.query.q" class="search-caption">“{{ route.query.q }}” 검색 결과 {{ filteredItems.length }}건</p><div class="list-panel"><IncidentList :incidents="filteredItems" /></div><p v-if="error" class="inline-error">{{ error }}</p></div></template>
