<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SeverityBadge from '../components/incident/SeverityBadge.vue'
import { listIncidents, updateWorkflowStage } from '../services/incident'
import type { IncidentRecord, WorkflowStage } from '../types/incident'

const route = useRoute()
const router = useRouter()
const columns: { key: WorkflowStage; label: string; description: string }[] = [
  { key: 'todo', label: 'Todo', description: '새 질문 · 담당자 확인 전' },
  { key: 'in_progress', label: 'In Progress', description: '원인 조사와 점검 진행' },
  { key: 'review', label: 'Review', description: '진단 결과와 조치 검토' },
  { key: 'done', label: 'Done', description: '원인과 성공한 조치 확인' },
]
const items = ref<IncidentRecord[]>([])
const loading = ref(true)
const busyId = ref('')
const draggedId = ref('')
const dragOver = ref<WorkflowStage | ''>('')
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

function stageOf(item: IncidentRecord): WorkflowStage {
  if (item.state.status === 'resolved') return 'done'
  if (item.state.workflowStage) return item.state.workflowStage
  if (item.state.status === 'investigating') return 'in_progress'
  if (item.state.status === 'action_required' || item.state.status === 'verifying') return 'review'
  return 'todo'
}

const visible = computed(() => {
  const query = String(route.query.q || '').trim().toLowerCase()
  return query ? items.value.filter(item => `${item.id} ${item.message} ${item.state.diagnosis}`.toLowerCase().includes(query)) : items.value
})
function cards(stage: WorkflowStage) { return visible.value.filter(item => stageOf(item) === stage) }

async function refresh() {
  try { items.value = await listIncidents(); error.value = '' }
  catch { error.value = 'Incident 보드를 불러오지 못했습니다.' }
  finally { loading.value = false }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 10000) })
onUnmounted(() => { if (timer) clearInterval(timer) })

async function move(item: IncidentRecord, stage: WorkflowStage) {
  if (stage === stageOf(item) || busyId.value) return
  if (stage === 'done') {
    await router.push({ path: `/incidents/${item.id}`, query: { resolve: '1' } })
    return
  }
  busyId.value = item.id
  error.value = ''
  try {
    const state = await updateWorkflowStage(item.id, stage)
    item.state = state
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '업무 단계를 변경하지 못했습니다.' }
  finally { busyId.value = '' }
}

function onDragStart(event: DragEvent, item: IncidentRecord) {
  draggedId.value = item.id
  event.dataTransfer?.setData('text/plain', item.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
async function onDrop(event: DragEvent, stage: WorkflowStage) {
  const id = event.dataTransfer?.getData('text/plain') || draggedId.value
  draggedId.value = ''
  dragOver.value = ''
  const item = items.value.find(record => record.id === id)
  if (item) await move(item, stage)
}
</script>

<template>
  <div class="board-page">
    <div class="page-eyebrow">OPERATIONS <span>·</span> INCIDENT BOARD</div>
    <div class="page-heading board-heading">
      <div><h1>Incident Board<span class="title-dot">.</span></h1><p>질문 하나가 카드 하나입니다. 조사를 진행하고, 결과를 검토한 뒤 해결 기록으로 완료하세요.</p></div>
      <RouterLink to="/diagnose" class="primary-button">＋ New diagnosis</RouterLink>
    </div>
    <div class="tab-links"><RouterLink to="/incidents">Board</RouterLink><RouterLink to="/incidents/list">Live list</RouterLink><RouterLink to="/incidents/active">Active</RouterLink><RouterLink to="/incidents/resolved">Resolved</RouterLink><RouterLink to="/incidents/examples">Examples</RouterLink></div>
    <p v-if="route.query.q" class="search-caption">“{{ route.query.q }}” 검색 결과 {{ visible.length }}건</p>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div class="kanban-board" aria-label="Incident 업무 단계">
      <section v-for="column in columns" :key="column.key" class="kanban-column" :class="{ 'drop-target': dragOver === column.key }" :aria-label="column.label"
        @dragover.prevent="dragOver = column.key" @drop.prevent="onDrop($event, column.key)">
        <header class="kanban-column-head"><div><h2>{{ column.label }} <span>{{ cards(column.key).length }}</span></h2><p>{{ column.description }}</p></div><i :class="column.key" /></header>
        <div class="kanban-cards">
          <article v-for="item in cards(column.key)" :key="item.id" class="kanban-card" :class="{ dragging: draggedId === item.id }"
            :draggable="column.key !== 'done' && item.state.status !== 'investigating'" @dragstart="onDragStart($event, item)" @dragend="draggedId = ''; dragOver = ''">
            <RouterLink :to="`/incidents/${item.id}`" class="kanban-card-link">
              <div class="kanban-card-meta"><strong>{{ item.id }}</strong><SeverityBadge :severity="item.state.severity" /></div>
              <h3>{{ item.message }}</h3>
              <p v-if="item.state.diagnosis" class="kanban-diagnosis">{{ item.state.diagnosis }}</p>
              <div class="kanban-card-foot"><span>{{ item.state.classification?.domain || 'UNKNOWN' }}</span><span>{{ new Date(item.updated_at).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' }) }}</span></div>
            </RouterLink>
            <div v-if="column.key !== 'done'" class="kanban-card-actions">
              <button v-if="column.key === 'in_progress'" type="button" :disabled="busyId === item.id || item.state.status === 'investigating'" @click="move(item, 'todo')">← Todo</button>
              <button v-if="column.key === 'review'" type="button" :disabled="busyId === item.id" @click="move(item, 'in_progress')">← In Progress</button>
              <button v-if="column.key === 'todo'" type="button" :disabled="busyId === item.id || item.state.status === 'investigating'" @click="move(item, 'in_progress')">In Progress →</button>
              <button v-if="column.key === 'in_progress'" type="button" :disabled="busyId === item.id || item.state.status === 'investigating'" @click="move(item, 'review')">Review →</button>
              <button v-if="column.key === 'review'" type="button" :disabled="busyId === item.id" @click="move(item, 'done')">해결 기록 →</button>
            </div>
          </article>
          <div v-if="!cards(column.key).length" class="kanban-empty">{{ loading ? '불러오는 중…' : '카드가 없습니다.' }}</div>
        </div>
      </section>
    </div>
    <p class="board-note">카드를 드래그하거나 버튼으로 옮길 수 있습니다. Done에는 원인과 실제 성공한 조치를 기록한 Incident만 들어갑니다.</p>
  </div>
</template>
