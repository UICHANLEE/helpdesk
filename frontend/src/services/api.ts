const BASE = '/api/v1'

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
  })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/') && window.location.pathname !== '/login') {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`)
    }
    let message = `요청 실패 (${response.status})`
    try { const body = await response.json(); message = body.detail || message } catch { /* use status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
