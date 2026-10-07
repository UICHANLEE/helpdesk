export type IncidentStatus = 'new' | 'investigating' | 'action_required' | 'verifying' | 'resolved'
export type Severity = 'P1' | 'P2' | 'P3' | 'P4'
export type Complexity = 'SIMPLE' | 'MEDIUM' | 'DEEP'

export interface Classification {
  domain: string
  secondary: string | null
  severity: Severity
  complexity: Complexity
  source: 'jev' | 'rules' | 'example'
  confidence: number | null
}

export interface Evidence {
  id: string
  source: string
  summary: string
  status: 'reported' | 'confirmed' | 'failed' | 'unavailable'
  data?: Record<string, unknown> | null
}

export interface Hypothesis {
  id: string
  name: string
  confidence: number | null
  rationale: string
}

export interface RaftMatch { id: string; title: string; summary: string; score: number | null; verification: 'verified' | 'unverified' | 'example' | 'unknown'; retrieval: 'hybrid' | 'lexical' | 'external' }
export interface AgentAction { id: string; label: string; tool: string | null; requires_approval: boolean; status: string }
export interface ClaimReference { eventId: number; relation: 'reported' | 'observed' | 'failed_check' | 'historical_match' | 'follow_up_check' | 'operator_verification' | 'example_scenario' }
export interface TraceClaim { id: string; text: string; verification: 'unverified' | 'operator_verified' | 'example'; references: ClaimReference[]; createdAt: string }

export interface IncidentState {
  id: string
  origin: 'live' | 'example'
  seedKey: string | null
  status: IncidentStatus
  severity: Severity
  symptoms: string[]
  confirmedFacts: Evidence[]
  unknowns: string[]
  hypotheses: Hypothesis[]
  rejectedHypotheses: Hypothesis[]
  raftMatches: RaftMatch[]
  actions: AgentAction[]
  currentStep: 'observe' | 'route' | 'retrieve' | 'reason' | 'act' | 'verify'
  classification: Classification | null
  diagnosis: string
  immediateActions: string[]
  reasoningTrace: Array<{ step: string; text: string }>
  recommendedAction: string
  providerStatus: Record<string, string>
  resolution: { rootCause: string; successfulAction: string; note: string; verifiedAt: string } | null
  traceId: string
  claims: TraceClaim[]
}

export interface IncidentRecord { id: string; message: string; state: IncidentState; created_at: string; updated_at: string }

export type TimelineType = 'user' | 'agent' | 'jev' | 'retrieval' | 'tool_started' | 'tool_result' | 'evidence' | 'reasoning_started' | 'reasoning' | 'action' | 'verified' | 'status_changed' | 'error'
export interface TimelineEvent { id: number; incident_id: string; type: TimelineType; data: Record<string, unknown>; created_at: string }
