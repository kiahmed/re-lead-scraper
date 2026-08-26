const TOKEN_KEY = 'flynest_public_token'
// same-origin by default (local dev proxy + SWA); set VITE_API_BASE only for a
// standalone Function App host
const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; query?: Record<string, string> } = {},
): Promise<T> {
  const params = options.query ? '?' + new URLSearchParams(options.query).toString() : ''
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
    // SWA strips Authorization before managed functions see it
    headers['X-Public-Token'] = token
  }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`${API_BASE}/api/${path}${params}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('auth/')) {
      clearToken()
      window.location.assign('/signin')
    }
    throw new ApiError(res.status, (data as { error?: string }).error ?? `HTTP ${res.status}`)
  }
  return data as T
}
