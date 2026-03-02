import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  CalendarDays, Route, MapPin, DollarSign, Footprints,
  BedDouble, Sun, CloudSun, CloudRain, CloudFog, CloudSnow,
  CloudLightning, Umbrella, Wind, Sunrise, Sunset, Users, Sparkles, Star, Utensils,
} from 'lucide-react'
import clsx from 'clsx'
import { useTripStore } from '../store/tripStore'
import { getItinerary, getTrip } from '../api/trips'
import { saveTrip } from '../api/savedTrips'
import { getPhotoUrl } from '../api/client'
import { useAuthStore } from '../store/authStore'
import Header from '../components/layout/Header'
import HeroImage from '../components/itinerary/HeroImage'
import ActivityItem from '../components/itinerary/ActivityItem'
import RouteMap from '../components/itinerary/RouteMap'
import { formatDistance, formatTime, formatDuration } from '../lib/utils'
import { getChronologicalDay, getChronologicalPoiBlocks } from '../lib/itinerary'
import { BUDGET_OPTIONS, PACE_OPTIONS } from '../lib/constants'
import { useTripWeather } from '../hooks/useTripWeather'
import {
  formatWeatherTime,
  getWeatherIconKey,
  getWeatherLabel,
  getWeatherMessage,
  isForecastLikelyAvailable,
} from '../lib/weather'

export default function ItineraryPage() {
  const { tripId } = useParams<{ tripId: string }>()
  const { itinerary, trip, setItinerary, setTrip } = useTripStore()
  const { isAuthenticated, openLoginModal } = useAuthStore()
  const [selectedDay, setSelectedDay] = useState(0)
  const [loading, setLoading] = useState(!itinerary)
  const [error, setError] = useState('')
  const [isSaved, setIsSaved] = useState(false)
  const [highlightedPoi, setHighlightedPoi] = useState<string | null>(null)

  const handleMarkerClick = useCallback((poiId: string) => {
    setHighlightedPoi(poiId)
    // Scroll to the POI card in the timeline
    const el = document.getElementById(`poi-${poiId}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  useEffect(() => {
    if (!tripId) return

    const loadData = async () => {
      try {
        if (!itinerary) {
          const data = await getItinerary(tripId)
          setItinerary(data)
        }
        if (!trip) {
          const tripData = await getTrip(tripId)
          setTrip(tripData)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load itinerary')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [tripId])

  const handleSave = async () => {
    if (!isAuthenticated) {
      openLoginModal()
      return
    }
    if (!tripId || !trip || !itinerary) return
    try {
      const photoRef = itinerary.city_photo_reference || trip.city_photo_reference
      await saveTrip({
        trip_id: tripId,
        city_name: trip.city,
        start_date: trip.start_date,
        end_date: trip.end_date,
        hero_image_url: photoRef ? getPhotoUrl(photoRef, 800) : undefined,
      })
      setIsSaved(true)
    } catch {
      setIsSaved(true)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-text-secondary">Loading itinerary...</p>
        </div>
      </div>
    )
  }

  if (error || !itinerary) {
    return (
      <div className="min-h-screen bg-base flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'No itinerary found'}</p>
          <a href="/" className="text-primary hover:underline">Go home</a>
        </div>
      </div>
    )
  }

  const selectedDayData = itinerary.days[selectedDay]
  const currentDay = getChronologicalDay(selectedDayData)
  const currentDayPoiBlocks = getChronologicalPoiBlocks(currentDay)
  const currentDayDistance = currentDay.blocks.reduce((sum, block) => sum + (block.travel_distance_meters || 0), 0)
  const firstPoi = currentDayPoiBlocks[0]
  const lastPoi = currentDayPoiBlocks.at(-1)
  const mealStops = currentDayPoiBlocks.filter((block) => block.block_type === 'meal').length
  const highestRatedStop = [...currentDayPoiBlocks]
    .filter((block) => typeof block.poi?.rating === 'number')
    .sort((a, b) => (b.poi?.rating ?? 0) - (a.poi?.rating ?? 0))[0]

  // Stats
  const totalDays = itinerary.days.length
  const dailyCost = trip?.budget === 'high' ? 250 : trip?.budget === 'medium' ? 120 : 60
  const estimatedCost = dailyCost * totalDays

  const currentDayCategories: Record<string, number> = {}
  currentDayPoiBlocks.forEach((block) => {
    const cat = block.poi?.category
    if (!cat) return
    currentDayCategories[cat] = (currentDayCategories[cat] || 0) + 1
  })

  const topDayCategories = Object.entries(currentDayCategories)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3)

  const paceLabel = PACE_OPTIONS.find((option) => option.value === trip?.pace)?.label || trip?.pace || 'Moderate'
  const budgetLabel = BUDGET_OPTIONS.find((option) => option.value === trip?.budget)?.label || trip?.budget || 'Comfort'

  const { forecast, isLoading: weatherLoading } = useTripWeather(
    trip?.city_center_lat,
    trip?.city_center_lon,
    currentDay.date
  )

  const weatherLabel = getWeatherLabel(forecast?.weatherCode)
  const weatherMessage = getWeatherMessage(forecast)
  const weatherIconKey = getWeatherIconKey(forecast?.weatherCode)
  const weatherAvailableSoon = isForecastLikelyAvailable(currentDay.date)
  const WeatherIcon = {
    sun: Sun,
    'cloud-sun': CloudSun,
    'cloud-rain': CloudRain,
    'cloud-fog': CloudFog,
    'cloud-snow': CloudSnow,
    'cloud-lightning': CloudLightning,
  }[weatherIconKey]

  return (
    <div className="min-h-screen bg-base">
      <Header />

      {/* Hero */}
      <div className="pt-16">
        <HeroImage
          cityName={trip?.city || 'Trip'}
          photoRef={itinerary.city_photo_reference || trip?.city_photo_reference || null}
          startDate={trip?.start_date || itinerary.days[0]?.date || ''}
          endDate={trip?.end_date || itinerary.days[itinerary.days.length - 1]?.date || ''}
          numTravelers={trip?.num_travelers || 1}
          onSave={handleSave}
          isSaved={isSaved}
        />
      </div>

      {/* Sticky header: day selector */}
      <div className="sticky top-16 z-20 bg-base/95 backdrop-blur-sm border-b border-border-default">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-3 overflow-x-auto no-scrollbar">
          <span className="text-white text-sm font-semibold whitespace-nowrap">Route by day</span>
          <div className="flex gap-1.5">
            {itinerary.days.map((day, idx) => (
              <button
                key={day.day_number}
                onClick={() => setSelectedDay(idx)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors shrink-0',
                  selectedDay === idx
                    ? 'bg-white/10 text-white'
                    : 'text-text-muted hover:text-white'
                )}
              >
                Day {day.day_number}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div>
        {currentDay && (
          <>
            <div className="max-w-7xl mx-auto px-6 py-6 space-y-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_360px]">
                <div className="bg-surface border border-border-default rounded-2xl p-5">
                  <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                    <div>
                      <p className="text-primary/80 text-[11px] font-semibold uppercase tracking-[0.18em]">
                        Trip Intel
                      </p>
                      <h2 className="text-2xl font-bold text-white mt-2">
                        Day {currentDay.day_number}: {currentDay.theme}
                      </h2>
                      <p className="text-text-muted text-sm mt-1">
                        {trip?.city || 'Your trip'} · {new Date(currentDay.date).toLocaleDateString('en-US', {
                          weekday: 'long',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {[
                        { icon: CalendarDays, label: `${totalDays} days` },
                        { icon: Users, label: `${trip?.num_travelers || 1} travelers` },
                        { icon: Sparkles, label: `${paceLabel} pace` },
                        { icon: DollarSign, label: `${budgetLabel} budget` },
                      ].map((item) => (
                        <div
                          key={item.label}
                          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-text-secondary"
                        >
                          <item.icon size={13} className="text-primary" />
                          {item.label}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2 mt-5">
                    {[
                      { icon: MapPin, label: `${currentDayPoiBlocks.length} places` },
                      { icon: Footprints, label: formatDistance(currentDayDistance) },
                      { icon: Route, label: firstPoi && lastPoi ? `${formatTime(firstPoi.start_time)} → ${formatTime(lastPoi.end_time)}` : 'Flexible timing' },
                      { icon: Utensils, label: `${mealStops} food stops` },
                      { icon: DollarSign, label: `~$${estimatedCost}` },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-2 text-sm text-white"
                      >
                        <item.icon size={14} className="text-primary" />
                        {item.label}
                      </div>
                    ))}
                  </div>

                  <div className="grid gap-3 md:grid-cols-3 mt-5">
                    <div className="rounded-xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/50">
                        Best Rated Stop
                      </p>
                      <p className="text-white font-semibold mt-2">
                        {highestRatedStop?.poi?.name || 'Route in progress'}
                      </p>
                      <p className="text-text-muted text-sm mt-1">
                        {highestRatedStop?.poi?.rating
                          ? `${highestRatedStop.poi.rating.toFixed(1)} stars from your selected route`
                          : 'The day mixes landmarks, food, and easy walking.'}
                      </p>
                    </div>

                    <div className="rounded-xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/50">
                        Route Rhythm
                      </p>
                      <p className="text-white font-semibold mt-2">
                        {firstPoi && lastPoi
                          ? `${formatTime(firstPoi.start_time)} to ${formatTime(lastPoi.end_time)}`
                          : 'Times flex with the day'}
                      </p>
                      <p className="text-text-muted text-sm mt-1">
                        {mealStops > 0
                          ? `${mealStops} planned meal stops help break up the walking.`
                          : 'The route stays focused on activities and landmarks.'}
                      </p>
                    </div>

                    <div className="rounded-xl border border-white/8 bg-black/20 p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/50">
                        Day Focus
                      </p>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {topDayCategories.length > 0 ? (
                          topDayCategories.map(([category, count]) => (
                            <span
                              key={category}
                              className="rounded-full bg-white/6 px-2.5 py-1 text-xs text-text-secondary"
                            >
                              {category} · {count}
                            </span>
                          ))
                        ) : (
                          <span className="rounded-full bg-white/6 px-2.5 py-1 text-xs text-text-secondary">
                            Flexible route
                          </span>
                        )}
                      </div>
                      <p className="text-text-muted text-sm mt-2">
                        The selected day leans into {currentDay.theme.toLowerCase()} without losing a comfortable pace.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-surface border border-border-default rounded-2xl p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-primary/80 text-[11px] font-semibold uppercase tracking-[0.18em]">
                        Weather
                      </p>
                      <h3 className="text-xl font-bold text-white mt-2">
                        {new Date(currentDay.date).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </h3>
                      <p className="text-text-muted text-sm mt-1">
                        {trip?.city || 'Destination'} walking conditions
                      </p>
                    </div>

                    <div className="w-12 h-12 rounded-2xl bg-primary/12 flex items-center justify-center shrink-0">
                      <WeatherIcon className="text-primary" size={24} />
                    </div>
                  </div>

                  {forecast ? (
                    <>
                      <div className="mt-4 flex items-end gap-3">
                        <div>
                          <p className="text-3xl font-bold text-white">
                            {Math.round(forecast.tempMax ?? 0)}°
                          </p>
                          <p className="text-text-secondary text-sm">
                            {forecast.tempMin != null ? `Low ${Math.round(forecast.tempMin)}°` : 'No low temp'}
                          </p>
                        </div>
                        <p className="text-text-muted text-sm pb-1">{weatherLabel}</p>
                      </div>

                      <p className="text-text-secondary text-sm leading-relaxed mt-4">
                        {weatherMessage}
                      </p>

                      <div className="grid grid-cols-2 gap-3 mt-4">
                        {[
                          {
                            icon: Umbrella,
                            label: 'Rain chance',
                            value: forecast.precipitationProbabilityMax != null
                              ? `${forecast.precipitationProbabilityMax}%`
                              : 'n/a',
                          },
                          {
                            icon: Wind,
                            label: 'Wind',
                            value: forecast.windSpeedMax != null
                              ? `${Math.round(forecast.windSpeedMax)} km/h`
                              : 'n/a',
                          },
                          {
                            icon: Sunrise,
                            label: 'Sunrise',
                            value: formatWeatherTime(forecast.sunrise) || 'n/a',
                          },
                          {
                            icon: Sunset,
                            label: 'Sunset',
                            value: formatWeatherTime(forecast.sunset) || 'n/a',
                          },
                        ].map((item) => (
                          <div key={item.label} className="rounded-xl border border-white/8 bg-black/20 p-3">
                            <div className="flex items-center gap-2 text-text-muted text-xs">
                              <item.icon size={13} className="text-primary" />
                              {item.label}
                            </div>
                            <p className="text-white font-semibold mt-2">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="mt-4 rounded-xl border border-white/8 bg-black/20 p-4">
                      <p className="text-white font-semibold">
                        {weatherLoading ? 'Loading forecast...' : 'Forecast not ready yet'}
                      </p>
                      <p className="text-text-secondary text-sm leading-relaxed mt-2">
                        {weatherAvailableSoon
                          ? 'The selected day is within the forecast window, so weather data should appear as soon as the request completes.'
                          : 'Detailed forecast is typically available up to 16 days ahead, so this card will become useful closer to the trip date.'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-col lg:flex-row max-w-7xl mx-auto px-6 pb-8" style={{ height: 'calc(100vh - 120px)' }}>
            {/* Left: Timeline */}
            <div className="lg:w-[420px] xl:w-[480px] shrink-0 overflow-y-auto pr-0 lg:pr-6 py-2 order-2 lg:order-1">
              {/* Day header */}
              <div className="mb-4">
                <h2 className="text-xl font-bold text-white">Stops for Day {currentDay.day_number}</h2>
                <div className="flex items-center gap-3 mt-1 text-text-muted text-sm">
                  <span className="flex items-center gap-1">
                    <MapPin size={13} />
                    {currentDayPoiBlocks.length} places
                  </span>
                  <span className="flex items-center gap-1">
                    <Footprints size={13} />
                    {formatDistance(currentDayDistance)}
                  </span>
                  {forecast && (
                    <span className="flex items-center gap-1">
                      <Sun size={13} />
                      {Math.round(forecast.tempMax ?? 0)}°
                    </span>
                  )}
                  {firstPoi && lastPoi && (
                    <span className="flex items-center gap-1">
                      <CalendarDays size={13} />
                      {formatDuration(
                        Math.max(
                          0,
                          ((Number.parseInt(lastPoi.end_time.split(':')[0], 10) * 60) + Number.parseInt(lastPoi.end_time.split(':')[1], 10)) -
                          ((Number.parseInt(firstPoi.start_time.split(':')[0], 10) * 60) + Number.parseInt(firstPoi.start_time.split(':')[1], 10))
                        )
                      )}
                    </span>
                  )}
                </div>
                <p className="text-text-secondary text-sm mt-2">
                  The day is built around {currentDay.theme.toLowerCase()}, with route details and context attached to each stop.
                </p>
                {topDayCategories.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {topDayCategories.map(([category, count]) => (
                      <span
                        key={category}
                        className="rounded-full border border-white/8 bg-white/5 px-2.5 py-1 text-xs text-text-secondary"
                      >
                        {category} · {count}
                      </span>
                    ))}
                  </div>
                )}
                {highestRatedStop?.poi && (
                  <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-text-secondary">
                    <Star size={12} className="text-primary" />
                    Best rated stop: <span className="text-white">{highestRatedStop.poi.name}</span>
                  </div>
                )}
              </div>

              {/* Timeline */}
              <div className="space-y-0">
                {currentDay.blocks
                  .filter((b) => b.poi || b.block_type === 'travel')
                  .map((block, idx, arr) => {
                    if (block.block_type === 'travel' && block.travel_time_from_prev) {
                      return (
                        <div key={`travel-${idx}`} className="flex items-center gap-3 py-2 pl-2">
                          <div className="w-6 flex justify-center">
                            <div className="w-px h-6 bg-primary/30" style={{ backgroundImage: 'repeating-linear-gradient(to bottom, transparent, transparent 3px, #f76b2e40 3px, #f76b2e40 6px)' }} />
                          </div>
                          <div className="flex items-center gap-1.5 bg-white/5 rounded-full px-2.5 py-1">
                            <Footprints size={12} className="text-primary" />
                            <span className="text-text-secondary text-xs font-medium">
                              {block.travel_time_from_prev} min
                            </span>
                            {block.travel_distance_meters ? (
                              <span className="text-text-muted text-xs">
                                · {formatDistance(block.travel_distance_meters)}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      )
                    }
                    if (block.poi) {
                      const poiBlocks = arr.filter((b) => b.poi)
                      const poiIdx = poiBlocks.indexOf(block)
                      return (
                        <div
                          key={block.poi.poi_id}
                          id={`poi-${block.poi.poi_id}`}
                          className={clsx(
                            'transition-all rounded-xl',
                            highlightedPoi === block.poi.poi_id && 'ring-1 ring-primary/50'
                          )}
                          onMouseEnter={() => setHighlightedPoi(block.poi!.poi_id)}
                          onMouseLeave={() => setHighlightedPoi(null)}
                        >
                          <ActivityItem
                            block={block}
                            isFirst={poiIdx === 0}
                            isLast={poiIdx === poiBlocks.length - 1}
                            index={poiIdx}
                            dayTheme={currentDay.theme}
                          />
                        </div>
                      )
                    }
                    return null
                  })}
              </div>

              {/* Book Accommodation CTA */}
              <div className="mt-6 pt-4 border-t border-border-default">
                <button className="w-full flex items-center justify-center gap-2 text-sm font-medium text-primary hover:text-white bg-primary/8 hover:bg-primary/15 border border-primary/20 rounded-xl py-3.5 transition-colors">
                  <BedDouble size={16} />
                  Find Accommodation for This Trip
                </button>
              </div>
            </div>

            {/* Right: Map (sticky on desktop, fixed height on mobile) */}
            <div className="flex-1 order-1 lg:order-2 h-64 lg:h-auto lg:sticky lg:top-[120px]">
              <RouteMap
                day={selectedDayData}
                highlightedPoi={highlightedPoi}
                onMarkerClick={handleMarkerClick}
              />
            </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
