import { useEffect, useState } from 'react'
import { getDailyWeatherForecast, type DailyWeatherForecast } from '../api/weather'

const weatherCache = new Map<string, DailyWeatherForecast | null>()
const pendingCache = new Map<string, Promise<DailyWeatherForecast | null>>()

function buildCacheKey(latitude: number, longitude: number, date: string) {
  return `${latitude.toFixed(4)}:${longitude.toFixed(4)}:${date}`
}

async function loadForecast(latitude: number, longitude: number, date: string) {
  const cacheKey = buildCacheKey(latitude, longitude, date)

  if (weatherCache.has(cacheKey)) {
    return weatherCache.get(cacheKey) ?? null
  }

  const pending = pendingCache.get(cacheKey)
  if (pending) return pending

  const request = getDailyWeatherForecast(latitude, longitude, date)
    .then((forecast) => {
      weatherCache.set(cacheKey, forecast)
      return forecast
    })
    .catch(() => null)
    .finally(() => {
      pendingCache.delete(cacheKey)
    })

  pendingCache.set(cacheKey, request)
  return request
}

export function useTripWeather(
  latitude: number | null | undefined,
  longitude: number | null | undefined,
  date: string | null | undefined
) {
  const cacheKey = latitude != null && longitude != null && date
    ? buildCacheKey(latitude, longitude, date)
    : null

  const [forecast, setForecast] = useState<DailyWeatherForecast | null>(() => {
    if (!cacheKey) return null
    return weatherCache.get(cacheKey) ?? null
  })
  const [isLoading, setIsLoading] = useState(() => Boolean(cacheKey && !weatherCache.has(cacheKey)))

  useEffect(() => {
    if (latitude == null || longitude == null || !date || !cacheKey) {
      setForecast(null)
      setIsLoading(false)
      return
    }

    if (weatherCache.has(cacheKey)) {
      setForecast(weatherCache.get(cacheKey) ?? null)
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)

    loadForecast(latitude, longitude, date).then((result) => {
      if (cancelled) return
      setForecast(result)
      setIsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [cacheKey, date, latitude, longitude])

  return { forecast, isLoading }
}
