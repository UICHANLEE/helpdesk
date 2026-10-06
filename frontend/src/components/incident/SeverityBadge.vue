<script setup lang="ts">defineProps<{ severity: string }>()</script>
<template><span class="severity-badge" :class="severity.toLowerCase()">{{ severity }}</span></template>
