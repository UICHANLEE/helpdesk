<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listTools } from '../services/tools'
import type { ToolInfo } from '../types/tools'
const props = defineProps<{ section: string; area: string }>()
const tools = ref<ToolInfo[]>([])
onMounted(async () => { if (props.section === 'tools') try { tools.value = await listTools() } catch { /* backend unavailable */ } })
</script>
<template><div class="page-wrap"><div class="page-eyebrow">{{ area.toUpperCase() }} <span>·</span> {{ section.toUpperCase() }}</div><div class="page-heading"><div><h1>{{ section[0].toUpperCase() + section.slice(1) }}<span class="title-dot">.</span></h1><p v-if="section === 'tools'">허용된 읽기 전용 점검 도구와 연결 상태입니다.</p><p v-else>이 화면은 핵심 진단 흐름에 연결할 준비가 되어 있습니다.</p></div></div><div v-if="section === 'tools'" class="list-panel"><div v-for="tool in tools" :key="tool.name" class="support-row"><strong>{{ tool.name }}</strong><span>{{ tool.mode }}</span><span class="connection-status" :class="tool.configured ? 'configured' : 'unconfigured'">● {{ tool.configured ? 'configured' : 'unconfigured' }}</span></div><div v-if="!tools.length" class="empty-state">도구 목록을 불러오지 못했습니다.</div></div><div v-else class="empty-panel"><span>◫</span><h2>Coming into focus</h2><p>Quick Diagnose와 Incident Workspace에서 생성된 정보가 이곳에 연결됩니다.</p><RouterLink to="/diagnose" class="secondary-button">Quick Diagnose 열기 →</RouterLink></div></div></template>
