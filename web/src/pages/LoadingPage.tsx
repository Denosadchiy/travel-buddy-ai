import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { MapPin, Utensils, Camera, Route, Star, Clock } from 'lucide-react'
import { generatePlan } from '../api/trips'
import { useTripStore } from '../store/tripStore'

const STEPS = [
  { icon: MapPin, text: 'Discovering hidden gems', color: '#f76b2e' },
  { icon: Route, text: 'Optimizing walking routes', color: '#3b82f6' },
  { icon: Utensils, text: 'Finding the best restaurants', color: '#22c55e' },
  { icon: Star, text: 'Checking real-time ratings', color: '#eab308' },
  { icon: Camera, text: 'Selecting must-see spots', color: '#a855f7' },
  { icon: Clock, text: 'Building day-by-day schedule', color: '#ec4899' },
]

export default function LoadingPage() {
  const { tripId } = useParams<{ tripId: string }>()
  const navigate = useNavigate()
  const { trip, setItinerary } = useTripStore()
  const [activeStep, setActiveStep] = useState(0)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [isRetrying, setIsRetrying] = useState(false)
  const hasStarted = useRef(false)

  // Cycle through steps
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStep((i) => (i + 1) % STEPS.length)
    }, 3500)
    return () => clearInterval(interval)
  }, [])

  // Simulate progress bar
  useEffect(() => {
    if (error) return
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 90) return 90 // Cap at 90% until real completion
        return p + Math.random() * 3 + 0.5
      })
    }, 500)
    return () => clearInterval(interval)
  }, [error])

  const generate = async () => {
    if (!tripId) return
    setError('')
    setProgress(5)
    try {
      const itinerary = await generatePlan(tripId)
      setProgress(100)
      setItinerary(itinerary)
      setTimeout(() => {
        navigate(`/itinerary/${tripId}`, { replace: true })
      }, 400)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate route')
    } finally {
      setIsRetrying(false)
    }
  }

  useEffect(() => {
    if (!hasStarted.current) {
      hasStarted.current = true
      generate()
    }
  }, [tripId])

  const handleRetry = () => {
    setIsRetrying(true)
    setProgress(0)
    generate()
  }

  const currentStep = STEPS[activeStep]
  const CurrentIcon = currentStep.icon

  return (
    <div className="min-h-screen bg-base flex flex-col items-center justify-center relative overflow-hidden">
      {/* Animated gradient orbs */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full opacity-[0.07] blur-3xl animate-[float_8s_ease-in-out_infinite]"
          style={{ background: 'radial-gradient(circle, #f76b2e, transparent 70%)' }}
        />
        <div
          className="absolute -bottom-40 -right-40 w-[500px] h-[500px] rounded-full opacity-[0.07] blur-3xl animate-[float_8s_ease-in-out_infinite_4s]"
          style={{ background: 'radial-gradient(circle, #3b82f6, transparent 70%)' }}
        />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full opacity-[0.05] blur-3xl animate-pulse"
          style={{ background: 'radial-gradient(circle, #a855f7, transparent 70%)' }}
        />
      </div>

      {/* Floating particles */}
      <div className="absolute inset-0 overflow-hidden">
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-1 h-1 rounded-full bg-primary/30 animate-[rise_6s_ease-in_infinite]"
            style={{
              left: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 6}s`,
              animationDuration: `${4 + Math.random() * 4}s`,
            }}
          />
        ))}
      </div>

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center px-6 max-w-lg w-full">
        {/* Animated icon */}
        <div className="relative mb-10">
          <div
            className="w-24 h-24 rounded-3xl flex items-center justify-center transition-all duration-700 ease-out"
            style={{
              background: `${currentStep.color}15`,
              boxShadow: `0 0 60px ${currentStep.color}20`,
            }}
          >
            <CurrentIcon
              size={40}
              className="transition-all duration-700 ease-out"
              style={{ color: currentStep.color }}
            />
          </div>
          {/* Orbiting dot */}
          <div className="absolute inset-0 animate-[spin_4s_linear_infinite]">
            <div
              className="absolute -top-1 left-1/2 w-2 h-2 rounded-full"
              style={{ background: currentStep.color }}
            />
          </div>
        </div>

        {/* City name */}
        {trip?.city && (
          <p className="text-4xl sm:text-5xl font-bold text-white mb-4 tracking-tight">
            {trip.city}
          </p>
        )}

        {/* Status text */}
        <p className="text-lg text-text-secondary mb-10 h-7 transition-opacity duration-500">
          {error ? '' : currentStep.text + '...'}
        </p>

        {/* Progress bar */}
        {!error && (
          <div className="w-full max-w-xs mb-8">
            <div className="h-1.5 bg-white/5 rounded-full overflow-hidden backdrop-blur-sm">
              <div
                className="h-full rounded-full transition-all duration-500 ease-out"
                style={{
                  width: `${Math.min(progress, 100)}%`,
                  background: `linear-gradient(90deg, ${currentStep.color}, #f76b2e)`,
                }}
              />
            </div>
            <p className="text-text-muted text-xs text-center mt-3">
              {progress < 30
                ? 'Analyzing your preferences...'
                : progress < 60
                  ? 'Finding perfect spots for you...'
                  : progress < 90
                    ? 'Almost there, finalizing your route...'
                    : 'Done!'}
            </p>
          </div>
        )}

        {/* Step indicators */}
        {!error && (
          <div className="flex gap-2">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className="h-1 rounded-full transition-all duration-500"
                style={{
                  width: i === activeStep ? 24 : 8,
                  background: i === activeStep ? currentStep.color : 'rgba(255,255,255,0.1)',
                }}
              />
            ))}
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="w-full bg-surface border border-red-500/20 rounded-2xl p-6 text-center">
            <p className="text-red-400 mb-5">{error}</p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => navigate(-1)}
                className="px-5 py-2.5 rounded-xl border border-white/10 text-text-secondary hover:text-white hover:bg-white/5 transition-colors text-sm font-medium"
              >
                Go Back
              </button>
              <button
                onClick={handleRetry}
                disabled={isRetrying}
                className="px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {isRetrying ? 'Retrying...' : 'Try Again'}
              </button>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translate(0, 0); }
          50% { transform: translate(30px, -30px); }
        }
        @keyframes rise {
          0% { transform: translateY(100vh) scale(0); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateY(-10vh) scale(1); opacity: 0; }
        }
      `}</style>
    </div>
  )
}
