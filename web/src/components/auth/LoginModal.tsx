import { useEffect, useState } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import { X } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { ApiError } from '../../api/client'
import { hasGoogleClientId } from '../../lib/env'
import EmailOTPForm from './EmailOTPForm'

function getAuthErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Google account verification failed. Please try another account.'
    if (error.status === 500) return 'Authentication is temporarily unavailable. Please try again.'
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Sign in failed. Please try again.'
}

export default function LoginModal() {
  const { showLoginModal, closeLoginModal, isLoading, loginWithGoogle } = useAuthStore()
  const [mode, setMode] = useState<'choice' | 'email'>('choice')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!showLoginModal) return
    setMode('choice')
    setError('')
  }, [showLoginModal])

  if (!showLoginModal) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={closeLoginModal}
      />

      {/* Modal */}
      <div className="relative bg-base/95 backdrop-blur-xl border border-white/10 rounded-2xl w-full max-w-md p-8 shadow-2xl">
        <button
          onClick={closeLoginModal}
          className="absolute top-4 right-4 text-text-muted hover:text-white transition-colors"
        >
          <X size={20} />
        </button>

        <div className="text-center mb-8">
          <img src="/logo-full.svg" alt="Locally" className="h-20 w-auto mx-auto mb-4" />
          <h2 className="text-2xl font-bold">Welcome to Locally</h2>
          <p className="text-text-secondary mt-2">Sign in to save trips and unlock all features</p>
        </div>

        {mode === 'choice' ? (
          <div className="space-y-3">
            {/* Google Sign-In */}
            {hasGoogleClientId ? (
              <div className="w-full overflow-hidden rounded-xl bg-white">
                <GoogleLogin
                  onSuccess={async (credentialResponse) => {
                    if (!credentialResponse.credential) {
                      setError('Google did not return an ID token. Please try again.')
                      return
                    }

                    setError('')
                    try {
                      await loginWithGoogle(credentialResponse.credential)
                    } catch (err) {
                      setError(getAuthErrorMessage(err))
                    }
                  }}
                  onError={() => setError('Google sign-in was cancelled or failed. Please try again.')}
                  text="continue_with"
                  shape="pill"
                  size="large"
                  theme="outline"
                />
              </div>
            ) : (
              <button
                disabled
                className="w-full flex items-center justify-center gap-3 bg-white/5 text-text-muted font-semibold py-3.5 rounded-xl border border-white/10 cursor-not-allowed"
              >
                Google sign-in unavailable
              </button>
            )}

            {error && <p className="text-red-400 text-sm">{error}</p>}
            {!hasGoogleClientId && (
              <p className="text-text-muted text-sm">
                Google sign-in for web requires <code>GOOGLE_CLIENT_ID_WEB</code> or <code>VITE_GOOGLE_CLIENT_ID</code>.
              </p>
            )}

            <div className="flex items-center gap-4 my-4">
              <div className="flex-1 h-px bg-white/10" />
              <span className="text-text-muted text-sm">or</span>
              <div className="flex-1 h-px bg-white/10" />
            </div>

            {/* Email OTP */}
            <button
              disabled={isLoading}
              onClick={() => {
                setError('')
                setMode('email')
              }}
              className="w-full bg-surface hover:bg-surface-hover border border-border-default text-white font-semibold py-3.5 rounded-xl transition-colors disabled:opacity-50"
            >
              Continue with Email
            </button>
          </div>
        ) : (
          <EmailOTPForm onBack={() => setMode('choice')} />
        )}
      </div>
    </div>
  )
}
