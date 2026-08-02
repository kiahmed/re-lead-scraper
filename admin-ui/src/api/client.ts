const TOKEN_KEY = 'soljet_admin_token'

export function getToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
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
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`/api/${path}${params}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401 && path !== 'auth/login') {
      clearToken()
      window.location.assign('/login')
    }
    throw new ApiError(res.status, (data as { error?: string }).error ?? `HTTP ${res.status}`)
  }
  return data as T
}
