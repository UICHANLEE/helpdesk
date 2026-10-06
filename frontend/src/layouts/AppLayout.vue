<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from '../components/app/AppSidebar.vue'
import AppTopbar from '../components/app/AppTopbar.vue'
const collapsed = ref(false)
</script>
<template>
  <div class="app-shell" :class="{ collapsed }">
    <AppSidebar :collapsed="collapsed" @toggle="collapsed = !collapsed" />
    <div class="app-main"><AppTopbar /><main class="page-content"><slot /></main></div>
  </div>
</template>
