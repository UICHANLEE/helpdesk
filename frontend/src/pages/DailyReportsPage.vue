<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getDailyReport, listDailyReports, type DailyReport } from '../services/knowledge'

const days = ref<DailyReport[]>([])
const selected = ref<DailyReport | null>(null)
const error = ref('')
async function choose(day: string) { try { selected.value = await getDailyReport(day); error.value = '' } catch { error.value = '보고서를 불러오지 못했습니다.' } }
onMounted(async () => { try { days.value = await listDailyReports(); if (days.value.length) await choose(days.value[0].date) } catch { error.value = '일별 기록을 불러오지 못했습니다.' } })
</script>
<template>
  <div class="page-wrap"><div class="page-eyebrow">DAILY WORK LOG</div><div class="page-heading"><div><h1>Daily Reports<span class="title-dot">.</span></h1><p>매일 질문·상황·조치를 엑셀로 남기고 업무 내용을 다시 확인합니다.</p></div><a v-if="selected" class="secondary-button" :href="`/api/v1/reports/daily/${selected.date}/xlsx`">{{ selected.date }} 엑셀 다운로드 ↓</a></div>
    <p v-if="error" class="inline-error">{{ error }}</p><div class="report-days"><button v-for="day in days" :key="day.date" class="secondary-button" :class="{ active: selected?.date === day.date }" @click="choose(day.date)">{{ day.date }} · {{ day.questions }}건</button></div>
    <div v-if="selected" class="surface-card report-summary"><span class="page-eyebrow">{{ selected.date }} · ASIA/SEOUL</span><h2>업무 요약</h2><p>{{ selected.summary }}</p></div>
    <div v-if="selected" class="section-heading"><h2>질문과 조치 기록</h2><small>{{ selected.records?.length }}건</small></div><div v-for="row in selected?.records" :key="row.incident_id" class="knowledge-item report-row"><div class="knowledge-item-top"><RouterLink :to="`/incidents/${row.incident_id}`">{{ row.incident_id }} →</RouterLink><small>{{ row.time }} · {{ row.domain }} · {{ row.status }}</small></div><p>{{ row.question }}</p><small>상황 · {{ row.situation }}</small><strong>진단 · {{ row.diagnosis }}</strong><small>제안된 조치 · {{ row.actions }}</small><small v-if="row.action_history">조치 결정 · {{ row.action_history }}</small><small v-if="row.successful_action">실제 성공한 조치 · {{ row.successful_action }}</small></div>
    <div v-if="!days.length && !error" class="empty-state">아직 기록된 질문이 없습니다.</div>
  </div>
</template>
