import { api } from './api'

export interface KnowledgeResult { id: string; type: string; question: string; answer: string; actions: string[]; score: number; status: 'verified' | 'unverified'; retrieval: 'hybrid' | 'lexical' }
export interface FrequentError { signature: string; domain: string; diagnosis: string; count: number; resolved: number; latest_at: string; example_incident_id: string; suggested_answer: string; faq_published: boolean }
export interface Faq { id: number; signature: string; question: string; answer: string; updated_at: string }
export interface KnowledgeData { stats: { questions: number; resolved_knowledge: number; faq_count: number; domains: Record<string, number>; vector: { model: string; indexed: number; storage: string } }; results: KnowledgeResult[]; frequent_errors: FrequentError[]; faq: Faq[] }
export interface DailyReport { date: string; summary: string; questions: number; resolved: number; domains: Record<string, number>; records?: Array<Record<string, string>> }
export interface StorageStatus { database_path: string; backup_dir: string; backup_count: number; latest_backup: string | null; latest_backup_at: string | null }
export interface SheetSyncResult { completed_at: string; updated_rows: number; inserted_rows: number; unchanged_rows: number; sheet_url: string }
export interface SheetSyncStatus { configured: boolean; service_account_email: string | null; credential_path: string; sheet_url: string; last_sync: SheetSyncResult | null }

export const getKnowledge = (query = '') => api<KnowledgeData>(`/knowledge?query=${encodeURIComponent(query)}`)
export const publishFaq = (body: { incident_id: string; question: string; answer: string }) => api<Faq>('/knowledge/faq', { method: 'POST', body: JSON.stringify(body) })
export const listDailyReports = () => api<DailyReport[]>('/reports/daily')
export const getDailyReport = (date: string) => api<DailyReport>(`/reports/daily/${date}`)
export const getStorageStatus = () => api<StorageStatus>('/reports/storage')
export const createBackup = () => api<StorageStatus>('/reports/backup', { method: 'POST' })
export const getSheetSyncStatus = () => api<SheetSyncStatus>('/reports/sheets/status')
export const syncGoogleSheet = () => api<SheetSyncResult>('/reports/sheets/sync', { method: 'POST' })
