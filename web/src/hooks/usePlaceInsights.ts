import { useEffect, useState } from 'react'
import { getPlaceDetails, pickBestPlacePhoto } from '../api/places'
import { getPhotoUrl } from '../api/client'
import type { PlaceDetailsResponse } from '../types/api'

const detailsCache = new Map<string, PlaceDetailsResponse | null>()
const pendingCache = new Map<string, Promise<PlaceDetailsResponse | null>>()

async function loadPlaceDetails(placeId: string): Promise<PlaceDetailsResponse | null> {
  if (detailsCache.has(placeId)) {
    return detailsCache.get(placeId) ?? null
  }

  const pending = pendingCache.get(placeId)
  if (pending) return pending

  const request = getPlaceDetails(placeId)
    .then((details) => {
      detailsCache.set(placeId, details)
      return details
    })
    .catch(() => null)
    .finally(() => {
      pendingCache.delete(placeId)
    })

  pendingCache.set(placeId, request)
  return request
}

export function usePlaceInsights(placeId: string | null | undefined, maxWidth = 800) {
  const [details, setDetails] = useState<PlaceDetailsResponse | null>(() => {
    if (!placeId) return null
    return detailsCache.get(placeId) ?? null
  })
  const [isLoading, setIsLoading] = useState(() => Boolean(placeId && !detailsCache.has(placeId)))

  useEffect(() => {
    if (!placeId) {
      setDetails(null)
      setIsLoading(false)
      return
    }

    if (detailsCache.has(placeId)) {
      setDetails(detailsCache.get(placeId) ?? null)
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)

    loadPlaceDetails(placeId).then((result) => {
      if (cancelled) return
      setDetails(result)
      setIsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [placeId])

  const bestPhoto = details ? pickBestPlacePhoto(details.photos) : null
  const photoUrl = bestPhoto ? getPhotoUrl(bestPhoto.id, maxWidth) : null

  return { details, photoUrl, isLoading }
}
