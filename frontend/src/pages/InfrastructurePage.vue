<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'
const props = defineProps<{ section?: string }>()
interface Service { name: string; status: string; note: string }
const data = ref<{ services: Service[]; qwen: string; jev: string; raft: string; storage: { backup_count: number; latest_backup: string | null } } | null>(null)
const visible = computed(() => props.section && props.section !== 'overview' ? data.value?.services.filter(item => item.name === props.section) : data.value?.services)
onMounted(async () => { try { data.value = await api('/infrastructure/overview') } catch { /* backend unavailable */ } })
</script>
<template><div class="page-wrap"><div class="page-eyebrow">SYSTEM TOPOLOGY <span>·</span> INFRASTRUCTURE</div><div class="page-heading"><div><h1>Infrastructure<span class="title-dot">.</span></h1><p>연결된 시스템과 점검 가능 여부를 확인합니다. 상태는 진단에서 도구를 실행해 검증합니다.</p></div></div><div class="tab-links"><RouterLink v-for="sectionName in ['overview','kubernetes','database','api','llm','storage']" :key="sectionName" :to="`/infrastructure/${sectionName}`">{{ sectionName }}</RouterLink></div><div class="infra-grid"><RouterLink v-for="service in visible" :key="service.name" :to="`/infrastructure/${service.name}`" class="infra-card"><div class="infra-card-top"><span class="infra-icon">⬡</span><span class="connection-status" :class="service.status">● {{ service.status }}</span></div><h2>{{ service.name }}</h2><p>{{ service.note }}</p></RouterLink></div><div class="provider-panel" v-if="data"><div v-for="name in ['jev','raft','qwen'] as const" :key="name"><small>{{ name.toUpperCase() }}</small><strong>{{ data[name] }}</strong></div><div><small>LOCAL BACKUP</small><strong>{{ data.storage.backup_count }} snapshots · {{ data.storage.latest_backup || 'pending' }}</strong></div></div></div></template>
