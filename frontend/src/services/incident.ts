import { api } from './api'
import type { Classification, IncidentRecord, IncidentState, TimelineEvent } from '../types/incident'

export const diagnose = (incidentId: string, message: string) => api<{ incident_id: string; classification: Classification }>('/diagnose', { method: 'POST', body: JSON.stringify({ incident_id: incidentId, message, attachments: [] }) })
export const createIncidentCard = (title: string) => api<IncidentRecord>('/incidents/cards', { method: 'POST', body: JSON.stringify({ title }) })
export const listIncidents = (status?: string) => api<IncidentRecord[]>(`/incidents${status ? `?status=${status}` : ''}`)
export const getIncident = (id: string) => api<IncidentRecord>(`/incidents/${encodeURIComponent(id)}`)
export const getState = (id: string) => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/state`)
export const getEvents = (id: string) => api<TimelineEvent[]>(`/incidents/${encodeURIComponent(id)}/events`)
export const updateIncidentStatus = (id: string, status: string, resolution?: { root_cause: string; successful_action: string; note: string }) => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/status`, { method: 'PATCH', body: JSON.stringify({ status, ...resolution }) })
export const updateWorkflowStage = (id: string, stage: 'todo' | 'in_progress' | 'review') => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/workflow`, { method: 'PATCH', body: JSON.stringify({ stage }) })
export const rehearseExample = (id: string) => api<{ incident_id: string; status: string }>(`/incidents/${encodeURIComponent(id)}/rehearse`, { method: 'POST' })
export const reviewExample = (id: string, resolution: { root_cause: string; successful_action: string; note: string }) => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/example-review`, { method: 'POST', body: JSON.stringify(resolution) })
