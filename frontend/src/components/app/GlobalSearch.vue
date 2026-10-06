<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()
const query = ref('')
const input = ref<HTMLInputElement | null>(null)
function shortcut(event: KeyboardEvent) { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); input.value?.focus() } }
function search() {
  const value = query.value.trim()
  if (!value) return
  const trace = /^TR-(INC-\d+)$/i.exec(value)
  if (trace) router.push(`/incidents/${trace[1].toUpperCase()}`)
  else router.push({ path: '/incidents', query: { q: value } })
}
onMounted(() => window.addEventListener('keydown', shortcut))
onUnmounted(() => window.removeEventListener('keydown', shortcut))
</script>
<template><form class="global-search" @submit.prevent="search"><span>⌕</span><input ref="input" v-model="query" placeholder="Incident / Trace ID 검색" aria-label="Incident 또는 Trace ID 검색" /><kbd>⌘ K</kbd></form></template>
