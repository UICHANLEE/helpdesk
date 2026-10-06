export interface ToolInfo { name: string; configured: boolean; mode: 'read_only' }
export interface ToolResult { name: string; status: 'ok' | 'error' | 'unconfigured'; summary: string; data?: Record<string, unknown> }
