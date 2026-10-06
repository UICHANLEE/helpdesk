<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../services/api'
import GlobalSearch from './GlobalSearch.vue'
const route = useRoute()
const title = computed(() => String(route.meta.title || 'RAFT'))
const status = ref<Record<string, string>>({})
onMounted(async () => { try { status.value = await api<Record<string, string>>('/infrastructure/overview').then(data => ({ qwen: data.qwen, jev: data.jev, raft: data.raft })) } catch { /* backend unavailable */ } })
</script>
<template>
  <header class="topbar"><div class="breadcrumb"><span>RAFT</span><span class="slash">/</span><strong>{{ title }}</strong></div><div class="topbar-right"><GlobalSearch /><div class="status-pills"><span v-for="name in ['qwen','jev','raft']" :key="name"><i :class="status[name] === 'configured' ? 'green' : ''"></i>{{ name.toUpperCase() }}</span></div><div class="avatar">U</div></div></header>
</template>
