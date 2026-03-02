import { getOrCreateDeviceId } from '../hooks/useDeviceId'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

let accessToken: string | null = localStorage.getItem('tb_access_token')
let refreshToken: string | null = localStorage.getItem('tb_refresh_token')
let isRefreshing = false
let refreshPromise: Promise<boolean> | null = null

export function setTokens(access: string, refresh: string) {
  accessToken = access
  refreshToken = refresh
  localStorage.setItem('tb_access_token', access)
  localStorage.setItem('tb_refresh_token', refresh)
}

export function clearTokens() {
  accessToken = null
  refreshToken = null
  localStorage.removeItem('tb_access_token')
  localStorage.removeItem('tb_refresh_token')
}

export function getAccessToken() {
  return accessToken
}

export function getRefreshToken() {
  return refreshToken
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false
  if (isRefreshing && refreshPromise) return refreshPromise

  isRefreshing = true
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!res.ok) {
        clearTokens()
        return false
      }
      const data = await res.json()
      setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      clearTokens()
      return false
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const deviceId = getOrCreateDeviceId()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Device-Id': deviceId,
    ...(options.headers as Record<string, string> || {}),
  }

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  let res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  // Auto-refresh on 401
  if (res.status === 401 && refreshToken) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      headers['Authorization'] = `Bearer ${accessToken}`
      res = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers,
      })
    }
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new ApiError(res.status, errorBody.detail || res.statusText, errorBody)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

export class ApiError extends Error {
  status: number
  body?: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export function getPhotoUrl(photoRef: string, maxWidth = 1200): string {
  return `${API_BASE_URL}/api/places/photos/${encodeURIComponent(photoRef)}?max_width=${maxWidth}`
}
