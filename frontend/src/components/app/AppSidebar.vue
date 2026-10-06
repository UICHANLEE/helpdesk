<script setup lang="ts">
defineProps<{ collapsed: boolean }>()
defineEmits<{ toggle: [] }>()
const sections = [
  { label: 'Dashboard', icon: '▦', to: '/dashboard' },
  { label: 'Diagnose', icon: '◇', to: '/diagnose' },
  { label: 'Incidents', icon: '◫', to: '/incidents' },
  { label: 'Infrastructure', icon: '⬡', to: '/infrastructure/overview' },
  { label: 'Knowledge', icon: '▤', to: '/knowledge/raft' },
  { label: 'FAQ', icon: '✦', to: '/faq' },
  { label: 'Daily Reports', icon: '▣', to: '/reports' },
  { label: 'Logs', icon: '≡', to: '/logs' },
  { label: 'Tools', icon: '⌘', to: '/tools' },
  { label: 'Audit', icon: '◷', to: '/audit' },
]
</script>
<template>
  <aside class="sidebar">
    <RouterLink to="/diagnose" class="brand"><span class="brand-icon">R</span><span v-if="!collapsed">RAFT <small>INCIDENT</small></span></RouterLink>
    <div class="sidebar-group-label" v-if="!collapsed">WORKSPACE</div>
    <nav class="sidebar-nav">
      <RouterLink v-for="item in sections" :key="item.to" :to="item.to" class="nav-item" :title="item.label"><span class="nav-icon">{{ item.icon }}</span><span v-if="!collapsed">{{ item.label }}</span></RouterLink>
    </nav>
    <div class="sidebar-bottom"><RouterLink to="/settings" class="nav-item" title="Settings"><span class="nav-icon">⚙</span><span v-if="!collapsed">Settings</span></RouterLink><button type="button" class="collapse-button" @click="$emit('toggle')">{{ collapsed ? '›' : '‹' }}</button></div>
  </aside>
</template>
