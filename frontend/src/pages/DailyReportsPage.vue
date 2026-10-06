<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  createBackup, getDailyReport, getSheetSyncStatus, getStorageStatus, listDailyReports,
  syncGoogleSheet, type DailyReport, type SheetSyncStatus, type StorageStatus,
} from '../services/knowledge'

const days = ref<DailyReport[]>([])
const selected = ref<DailyReport | null>(null)
const error = ref('')
const syncMessage = ref('')
const storage = ref<StorageStatus | null>(null)
const sheets = ref<SheetSyncStatus | null>(null)
const backingUp = ref(false)
const syncing = ref(false)

async function choose(day: string) {
  try { selected.value = await getDailyReport(day); error.value = '' }
  catch { error.value = '보고서를 불러오지 못했습니다.' }
}
async function backupNow() {
  backingUp.value = true
  try { storage.value = await createBackup(); error.value = '' }
  catch { error.value = '데이터베이스를 백업하지 못했습니다.' }
  finally { backingUp.value = false }
}
async function uploadNow() {
  syncing.value = true
  syncMessage.value = ''
  try {
    const result = await syncGoogleSheet()
    sheets.value = await getSheetSyncStatus()
    syncMessage.value = `업로드 완료 · 새 항목 ${result.inserted_rows}건, 갱신 ${result.updated_rows}건`
  } catch (cause) {
    syncMessage.value = cause instanceof Error ? cause.message : 'Google Sheet 업로드에 실패했습니다.'
  } finally { syncing.value = false }
}
onMounted(async () => {
  try {
    [days.value, storage.value, sheets.value] = await Promise.all([listDailyReports(), getStorageStatus(), getSheetSyncStatus()])
    if (days.value.length) await choose(days.value[0].date)
  } catch { error.value = '일별 기록을 불러오지 못했습니다.' }
})
</script>

<template>
  <div class="page-wrap">
    <div class="page-eyebrow">DAILY WORK LOG</div>
    <div class="page-heading"><div><h1>Daily Reports<span class="title-dot">.</span></h1><p>매일 질문·상황·조치를 엑셀로 남기고 업무 내용을 다시 확인합니다.</p></div><a v-if="selected" class="secondary-button" :href="`/api/v1/reports/daily/${selected.date}/xlsx`">{{ selected.date }} 엑셀 다운로드 ↓</a></div>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="storage" class="surface-card storage-summary"><div><small>로컬 데이터베이스 · {{ storage.database_path }}</small><strong>백업 {{ storage.backup_count }}개 · 최근 {{ storage.latest_backup || '없음' }}</strong><small>보관 폴더 · {{ storage.backup_dir }}</small></div><button class="secondary-button" :disabled="backingUp" @click="backupNow">{{ backingUp ? '백업 중…' : '지금 백업' }}</button></div>
    <div v-if="sheets" class="surface-card sheet-sync-card">
      <div><small>GOOGLE SHEET · 매일 16:50 자동 동기화</small><strong>질문 로그 · 일별 요약 · FAQ</strong><small v-if="sheets.last_sync">마지막 앱 업로드 · {{ new Date(sheets.last_sync.completed_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) }}</small><small v-else>앱에서 업로드한 기록 없음</small><small v-if="!sheets.configured">이 대화에서 “지금 업로드”라고 요청하면 즉시 반영됩니다. 앱 버튼은 별도 Google 인증 파일이 필요합니다: {{ sheets.credential_path }}</small><small v-else>앱 업로드 계정 · {{ sheets.service_account_email }}</small><small v-if="syncMessage" class="sync-feedback">{{ syncMessage }}</small></div>
      <div class="sheet-sync-actions"><a class="secondary-button" :href="sheets.sheet_url" target="_blank" rel="noopener noreferrer">시트 열기 ↗</a><button class="secondary-button" :disabled="syncing || !sheets.configured" @click="uploadNow">{{ syncing ? '업로드 중…' : sheets.configured ? '지금 업로드' : '앱 연결 필요' }}</button></div>
    </div>
    <div class="report-days"><button v-for="day in days" :key="day.date" class="secondary-button" :class="{ active: selected?.date === day.date }" @click="choose(day.date)">{{ day.date }} · {{ day.questions }}건</button></div>
    <div v-if="selected" class="surface-card report-summary"><span class="page-eyebrow">{{ selected.date }} · ASIA/SEOUL</span><h2>업무 요약</h2><p>{{ selected.summary }}</p></div>
    <div v-if="selected" class="section-heading"><h2>질문과 조치 기록</h2><small>{{ selected.records?.length }}건</small></div>
    <div v-for="row in selected?.records" :key="row.incident_id" class="knowledge-item report-row"><div class="knowledge-item-top"><RouterLink :to="`/incidents/${row.incident_id}`">{{ row.incident_id }} →</RouterLink><small>{{ row.time }} · {{ row.domain }} · {{ row.status }}</small></div><p>{{ row.question }}</p><small>상황 · {{ row.situation }}</small><strong>진단 · {{ row.diagnosis }}</strong><small>제안된 조치 · {{ row.actions }}</small><small v-if="row.action_history">조치 결정 · {{ row.action_history }}</small><small v-if="row.successful_action">실제 성공한 조치 · {{ row.successful_action }}</small></div>
    <div v-if="!days.length && !error" class="empty-state">아직 기록된 질문이 없습니다.</div>
  </div>
</template>
