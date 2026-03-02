import { create } from 'zustand'
import { googleLogout } from '@react-oauth/google'
import type { EmailStartResponse, User } from '../types/api'
import { setTokens, clearTokens, getRefreshToken } from '../api/client'
import * as authApi from '../api/auth'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  showLoginModal: boolean

  loginWithGoogle: (idToken: string) => Promise<void>
  startEmailOTP: (email: string) => Promise<EmailStartResponse>
  verifyEmailOTP: (challengeId: string, code: string) => Promise<void>
  restoreSession: () => Promise<void>
  logout: () => void
  openLoginModal: () => void
  closeLoginModal: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  showLoginModal: false,

  loginWithGoogle: async (idToken: string) => {
    set({ isLoading: true })
    try {
      const session = await authApi.googleLogin(idToken)
      setTokens(session.access_token, session.refresh_token)
      set({ user: session.user, isAuthenticated: true, isLoading: false, showLoginModal: false })
    } catch (err) {
      set({ isLoading: false })
      throw err
    }
  },

  startEmailOTP: async (email: string) => {
    set({ isLoading: true })
    try {
      const result = await authApi.emailStart(email)
      set({ isLoading: false })
      return result
    } catch (err) {
      set({ isLoading: false })
      throw err
    }
  },

  verifyEmailOTP: async (challengeId: string, code: string) => {
    set({ isLoading: true })
    try {
      const session = await authApi.emailVerify(challengeId, code)
      setTokens(session.access_token, session.refresh_token)
      set({ user: session.user, isAuthenticated: true, isLoading: false, showLoginModal: false })
    } catch (err) {
      set({ isLoading: false })
      throw err
    }
  },

  restoreSession: async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return

    set({ isLoading: true })
    try {
      const session = await authApi.refreshTokenApi(refreshToken)
      setTokens(session.access_token, session.refresh_token)
      set({ user: session.user, isAuthenticated: true, isLoading: false })
    } catch {
      clearTokens()
      set({ isLoading: false })
    }
  },

  logout: () => {
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => {})
    }
    try {
      googleLogout()
    } catch {
      // Ignore Google SDK absence; local tokens are the source of truth here.
    }
    clearTokens()
    set({ user: null, isAuthenticated: false, isLoading: false, showLoginModal: false })
  },

  openLoginModal: () => set({ showLoginModal: true }),
  closeLoginModal: () => set({ showLoginModal: false }),
}))
