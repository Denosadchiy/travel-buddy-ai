import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'
import CityAutocomplete from '../components/trip-form/CityAutocomplete'
import DateRangePicker from '../components/trip-form/DateRangePicker'
import TravelersInput from '../components/trip-form/TravelersInput'
import InterestsPicker from '../components/trip-form/InterestsPicker'
import BudgetSelector from '../components/trip-form/BudgetSelector'
import PaceSelector from '../components/trip-form/PaceSelector'
import PreferencesTextarea from '../components/trip-form/PreferencesTextarea'
import { useTripStore } from '../store/tripStore'
import { createTrip } from '../api/trips'

export default function PlanTripPage() {
  const navigate = useNavigate()
  const { form, updateForm, toggleInterest, setTrip, toCreateRequest } = useTripStore()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const isValid = form.city.trim() && form.startDate && form.endDate

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('[PlanTrip] Submit clicked, isValid:', isValid, 'form:', form)
    if (!isValid || isSubmitting) return

    setIsSubmitting(true)
    setError('')
    try {
      const req = toCreateRequest()
      console.log('[PlanTrip] Creating trip:', req)
      const trip = await createTrip(req)
      console.log('[PlanTrip] Trip created:', trip.id)
      setTrip(trip)
      navigate(`/plan/loading/${trip.id}`)
    } catch (err) {
      console.error('[PlanTrip] Error creating trip:', err)
      setError(err instanceof Error ? err.message : 'Failed to create trip. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-warm-gradient relative bg-noise">
      <Header />
      <main className="pt-24 pb-16">
        <div className="max-w-3xl mx-auto px-6">
          {/* Page Header */}
          <div className="text-center mb-12">
            <span className="text-primary text-xs font-semibold uppercase tracking-widest">
              Plan Your Trip
            </span>
            <h1 className="text-3xl sm:text-4xl font-bold mt-3">Where are you going?</h1>
            <p className="text-text-secondary mt-3 text-lg">Tell us about your travel plans...</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-8">
            <CityAutocomplete
              value={form.city}
              onChange={(city) => updateForm({ city })}
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <DateRangePicker
                startDate={form.startDate}
                endDate={form.endDate}
                onStartChange={(startDate) => updateForm({ startDate })}
                onEndChange={(endDate) => updateForm({ endDate })}
              />
              <TravelersInput
                value={form.numTravelers}
                onChange={(numTravelers) => updateForm({ numTravelers })}
              />
            </div>

            <InterestsPicker
              selected={form.interests}
              onToggle={toggleInterest}
            />

            <BudgetSelector
              value={form.budget}
              onChange={(budget) => updateForm({ budget })}
            />

            <PaceSelector
              value={form.pace}
              onChange={(pace) => updateForm({ pace })}
            />

            <PreferencesTextarea
              value={form.additionalPreferences}
              onChange={(additionalPreferences) => updateForm({ additionalPreferences })}
            />

            {error && (
              <p className="text-red-400 text-sm text-center">{error}</p>
            )}

            {!isValid && (
              <p className="text-text-muted text-sm text-center">
                Please fill in: {!form.city.trim() && 'destination'}{!form.city.trim() && (!form.startDate || !form.endDate) ? ', ' : ''}{!form.startDate && 'start date'}{!form.startDate && !form.endDate ? ', ' : ''}{!form.endDate && 'end date'}
              </p>
            )}

            <button
              type="submit"
              disabled={!isValid || isSubmitting}
              className="w-full bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-4 rounded-xl text-lg transition-all flex items-center justify-center gap-2"
            >
              <Sparkles size={20} />
              {isSubmitting ? 'Creating Trip...' : 'Generate My Itinerary'}
            </button>
            <p className="text-text-muted text-sm text-center">
              Usually takes 30–60 seconds to generate a full plan.
            </p>
          </form>
        </div>
      </main>

      <Footer />
    </div>
  )
}
