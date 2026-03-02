import { useEffect, useState } from 'react'
import { getBestPlacePhotoUrl } from '../api/places'

const photoCache = new Map<string, string | null>()
const pendingCache = new Map<string, Promise<string | null>>()

function getCacheKey(placeId: string, maxWidth: number): string {
  return `${placeId}:${maxWidth}`
}

export function usePlacePhoto(placeId: string | null | undefined, maxWidth = 800) {
  const cacheKey = placeId ? getCacheKey(placeId, maxWidth) : null
  const [photoUrl, setPhotoUrl] = useState<string | null>(() => {
    if (!cacheKey) return null
    return photoCache.get(cacheKey) ?? null
  })
  const [isLoading, setIsLoading] = useState(() => {
    if (!cacheKey) return false
    return !photoCache.has(cacheKey)
  })

  useEffect(() => {
    if (!placeId || !cacheKey) {
      setPhotoUrl(null)
      setIsLoading(false)
      return
    }

    if (photoCache.has(cacheKey)) {
      setPhotoUrl(photoCache.get(cacheKey) ?? null)
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)

    const pendingRequest = pendingCache.get(cacheKey) ?? getBestPlacePhotoUrl(placeId, maxWidth)
      .then((url) => {
        photoCache.set(cacheKey, url)
        return url
      })
      .catch(() => {
        return null
      })
      .finally(() => {
        pendingCache.delete(cacheKey)
      })

    pendingCache.set(cacheKey, pendingRequest)

    pendingRequest.then((url) => {
      if (cancelled) return
      setPhotoUrl(url)
      setIsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [cacheKey, maxWidth, placeId])

  return { photoUrl, isLoading }
}
