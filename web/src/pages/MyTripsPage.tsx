import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapPin, CalendarDays, Plus, Loader2 } from 'lucide-react'
import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'
import { useAuthStore } from '../store/authStore'
import { getSavedTrips } from '../api/savedTrips'
import { formatDateRange } from '../lib/utils'
import type { SavedTripResponse } from '../types/api'

export default function MyTripsPage() {
  const { isAuthenticated, openLoginModal } = useAuthStore()
  const [trips, setTrips] = useState<SavedTripResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false)
      return
    }

    const loadTrips = async () => {
      try {
        const data = await getSavedTrips()
        setTrips(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load trips')
      } finally {
        setLoading(false)
      }
    }

    loadTrips()
  }, [isAuthenticated])

  return (
    <div className="min-h-screen bg-base flex flex-col">
      <Header />

      <main className="flex-1 pt-24 pb-12 px-6">
        <div className="max-w-5xl mx-auto">
          {/* Page Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold text-white">My Trips</h1>
              <p className="text-text-secondary mt-1">Your saved travel plans</p>
            </div>
            <Link
              to="/plan"
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-semibold px-5 py-2.5 rounded-full transition-colors no-underline text-sm"
            >
              <Plus size={18} />
              New Trip
            </Link>
          </div>

          {/* Content */}
          {!isAuthenticated ? (
            <div className="bg-surface border border-border-default rounded-2xl p-12 text-center">
              <MapPin className="w-12 h-12 text-text-muted mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">Sign in to see your trips</h2>
              <p className="text-text-secondary mb-6 max-w-md mx-auto">
                Create an account to save your itineraries and access them from any device.
              </p>
              <button
                onClick={openLoginModal}
                className="bg-primary hover:bg-primary-hover text-white font-semibold px-6 py-3 rounded-xl transition-colors"
              >
                Sign In
              </button>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
            </div>
          ) : error ? (
            <div className="bg-surface border border-red-500/20 rounded-2xl p-8 text-center">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={() => window.location.reload()}
                className="text-primary hover:underline"
              >
                Try again
              </button>
            </div>
          ) : trips.length === 0 ? (
            <div className="bg-surface border border-border-default rounded-2xl p-12 text-center">
              <MapPin className="w-12 h-12 text-text-muted mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">No trips yet</h2>
              <p className="text-text-secondary mb-6">
                Plan your first trip and it will appear here.
              </p>
              <Link
                to="/plan"
                className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-semibold px-6 py-3 rounded-xl transition-colors no-underline"
              >
                <Plus size={18} />
                Plan Your First Trip
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {trips.map((trip) => (
                <Link
                  key={trip.id}
                  to={`/itinerary/${trip.trip_id}`}
                  className="group bg-surface border border-border-default rounded-2xl overflow-hidden hover:border-white/15 transition-all no-underline"
                >
                  {/* Image */}
                  <div className="h-40 bg-gradient-to-br from-primary/20 to-base relative overflow-hidden">
                    {trip.hero_image_url && (
                      <img
                        src={trip.hero_image_url}
                        alt={trip.city_name}
                        className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                    <div className="absolute bottom-3 left-4">
                      <h3 className="text-lg font-bold text-white">{trip.city_name}</h3>
                    </div>
                  </div>

                  {/* Info */}
                  <div className="p-4">
                    <div className="flex items-center gap-2 text-text-secondary text-sm">
                      <CalendarDays size={14} />
                      <span>{formatDateRange(trip.start_date, trip.end_date)}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}
