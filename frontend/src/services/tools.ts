import { api } from './api'
import type { ToolInfo, ToolResult } from '../types/tools'

export const listTools = () => api<ToolInfo[]>('/tools')
export const executeTool = (incidentId: string, tool: string) => api<ToolResult>('/tools/execute', { method: 'POST', body: JSON.stringify({ incident_id: incidentId, tool, arguments: {} }) })
