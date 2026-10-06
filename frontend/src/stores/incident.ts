import { reactive } from 'vue'
import type { IncidentRecord, TimelineEvent } from '../types/incident'
import { getEvents, getIncident, listIncidents } from '../services/incident'

export const incidentStore = reactive({
  items: [] as IncidentRecord[],
  current: null as IncidentRecord | null,
  events: [] as TimelineEvent[],
  loading: false,
})
let refreshTimer: ReturnType<typeof setTimeout> | null = null

export async function refreshIncidents(status?: string) { incidentStore.items = await listIncidents(status) }
export async function loadIncident(id: string) {
  incidentStore.loading = true
  try {
    const [record, events] = await Promise.all([getIncident(id), getEvents(id)])
    incidentStore.current = record
    incidentStore.events = events
  } finally { incidentStore.loading = false }
}
export function applyEvent(event: TimelineEvent) {
  if (!incidentStore.events.some(item => item.id === event.id)) incidentStore.events.push(event)
  if (incidentStore.current?.id === event.incident_id) {
    if (refreshTimer) clearTimeout(refreshTimer)
    refreshTimer = setTimeout(async () => { try { incidentStore.current = await getIncident(event.incident_id) } catch { /* keep last state */ } refreshTimer = null }, 80)
  }
}
