import { api } from './api'

export interface KnowledgeResult { id: string; type: string; question: string; answer: string; actions: string[]; score: number }
export interface FrequentError { signature: string; domain: string; diagnosis: string; count: number; resolved: number; latest_at: string; example_incident_id: string; suggested_answer: string; faq_published: boolean }
export interface Faq { id: number; signature: string; question: string; answer: string; updated_at: string }
export interface KnowledgeData { stats: { questions: number; resolved_knowledge: number; faq_count: number; domains: Record<string, number> }; results: KnowledgeResult[]; frequent_errors: FrequentError[]; faq: Faq[] }
export interface DailyReport { date: string; summary: string; questions: number; resolved: number; domains: Record<string, number>; records?: Array<Record<string, string>> }

export const getKnowledge = (query = '') => api<KnowledgeData>(`/knowledge?query=${encodeURIComponent(query)}`)
export const publishFaq = (body: { incident_id: string; question: string; answer: string }) => api<Faq>('/knowledge/faq', { method: 'POST', body: JSON.stringify(body) })
export const listDailyReports = () => api<DailyReport[]>('/reports/daily')
export const getDailyReport = (date: string) => api<DailyReport>(`/reports/daily/${date}`)
