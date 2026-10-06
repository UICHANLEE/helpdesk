import { api } from './api'
import type { Classification, IncidentRecord, IncidentState, TimelineEvent } from '../types/incident'

export const diagnose = (message: string) => api<{ incident_id: string; classification: Classification }>('/diagnose', { method: 'POST', body: JSON.stringify({ message, attachments: [] }) })
export const listIncidents = (status?: string) => api<IncidentRecord[]>(`/incidents${status ? `?status=${status}` : ''}`)
export const getIncident = (id: string) => api<IncidentRecord>(`/incidents/${encodeURIComponent(id)}`)
export const getState = (id: string) => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/state`)
export const getEvents = (id: string) => api<TimelineEvent[]>(`/incidents/${encodeURIComponent(id)}/events`)
export const updateIncidentStatus = (id: string, status: string, resolution?: { root_cause: string; successful_action: string; note: string }) => api<IncidentState>(`/incidents/${encodeURIComponent(id)}/status`, { method: 'PATCH', body: JSON.stringify({ status, ...resolution }) })
