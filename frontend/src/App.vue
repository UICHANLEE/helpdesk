<script setup lang="ts">
import AppLayout from './layouts/AppLayout.vue'
</script>
<template><RouterView v-if="$route.path === '/login'" /><AppLayout v-else><RouterView /></AppLayout></template>
