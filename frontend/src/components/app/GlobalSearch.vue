<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()
const query = ref('')
const input = ref<HTMLInputElement | null>(null)
function shortcut(event: KeyboardEvent) { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); input.value?.focus() } }
function search() { if (query.value.trim()) router.push({ path: '/incidents', query: { q: query.value.trim() } }) }
onMounted(() => window.addEventListener('keydown', shortcut))
onUnmounted(() => window.removeEventListener('keydown', shortcut))
</script>
<template><form class="global-search" @submit.prevent="search"><span>⌕</span><input ref="input" v-model="query" placeholder="Search incidents" aria-label="Incident 검색" /><kbd>⌘ K</kbd></form></template>
