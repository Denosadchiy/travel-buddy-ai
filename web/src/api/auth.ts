import { apiFetch } from './client'
import type { EmailStartResponse, SessionResponse, User } from '../types/api'

export function googleLogin(idToken: string): Promise<SessionResponse> {
  return apiFetch('/api/auth/google', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken }),
  })
}

export function emailStart(email: string): Promise<EmailStartResponse> {
  return apiFetch('/api/auth/email/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function emailVerify(challengeId: string, code: string): Promise<SessionResponse> {
  return apiFetch('/api/auth/email/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, code }),
  })
}

export function refreshTokenApi(refreshToken: string): Promise<SessionResponse> {
  return apiFetch('/api/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}

export function logout(refreshToken?: string): Promise<void> {
  return apiFetch('/api/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
}

export function getMe(): Promise<User> {
  return apiFetch('/api/auth/me')
}
