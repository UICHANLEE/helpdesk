import type { TimelineEvent, TimelineType } from '../types/incident'

const TYPES: TimelineType[] = ['user', 'agent', 'jev', 'retrieval', 'tool_started', 'tool_result', 'evidence', 'reasoning_started', 'reasoning', 'action', 'verified', 'status_changed', 'error']

export function watchIncident(id: string, onEvent: (event: TimelineEvent) => void, onError?: () => void): EventSource {
  const source = new EventSource(`/api/v1/incidents/${encodeURIComponent(id)}/stream`)
  TYPES.forEach(type => source.addEventListener(type, event => {
    try { onEvent(JSON.parse((event as MessageEvent).data) as TimelineEvent) } catch { /* ignore malformed event */ }
  }))
  source.onerror = () => onError?.()
  return source
}
