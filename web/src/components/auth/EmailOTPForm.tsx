import { useState } from 'react'
import { ArrowLeft, Mail } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { ApiError } from '../../api/client'

interface Props {
  onBack: () => void
}

export default function EmailOTPForm({ onBack }: Props) {
  const { startEmailOTP, verifyEmailOTP, isLoading } = useAuthStore()
  const [step, setStep] = useState<'email' | 'code'>('email')
  const [email, setEmail] = useState('')
  const [challengeId, setChallengeId] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [debugCode, setDebugCode] = useState('')

  const getErrorMessage = (fallback: string, err: unknown) => {
    if (err instanceof ApiError) return err.message || fallback
    if (err instanceof Error) return err.message || fallback
    return fallback
  }

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setInfo('')
    setDebugCode('')
    try {
      const result = await startEmailOTP(email)
      setChallengeId(result.challenge_id)
      setInfo(result.message)
      setDebugCode(result.debug_code ?? '')
      setCode(result.debug_code ?? '')
      setStep('code')
    } catch (err) {
      setError(getErrorMessage('Failed to send code. Please try again.', err))
    }
  }

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      await verifyEmailOTP(challengeId, code)
    } catch (err) {
      setError(getErrorMessage('Invalid code. Please try again.', err))
    }
  }

  return (
    <div>
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-text-secondary hover:text-white text-sm mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Back
      </button>

      {step === 'email' ? (
        <form onSubmit={handleSendCode} className="space-y-4">
          <div>
            <label className="block text-sm text-text-secondary mb-2">Email address</label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full bg-white/5 border border-border-default rounded-xl pl-10 pr-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
              />
            </div>
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={isLoading || !email}
            className="w-full bg-primary hover:bg-primary-hover text-white font-semibold py-3.5 rounded-xl transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Sending...' : 'Send Code'}
          </button>
        </form>
      ) : (
        <form onSubmit={handleVerifyCode} className="space-y-4">
          <p className="text-text-secondary text-sm">
            {info || (
              <>
                We sent a 6-digit code to <span className="text-white font-medium">{email}</span>
              </>
            )}
          </p>
          {debugCode && (
            <div className="rounded-xl border border-primary/30 bg-primary/10 px-4 py-3">
              <p className="text-xs uppercase tracking-[0.18em] text-primary/80">One-Time Code</p>
              <p className="mt-1 font-mono text-lg text-white">{debugCode}</p>
            </div>
          )}
          <div>
            <label className="block text-sm text-text-secondary mb-2">Verification code</label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              required
              className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white text-center text-2xl tracking-[0.5em] font-mono placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={isLoading || code.length < 6}
            className="w-full bg-primary hover:bg-primary-hover text-white font-semibold py-3.5 rounded-xl transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Verifying...' : 'Verify'}
          </button>
        </form>
      )}
    </div>
  )
}
