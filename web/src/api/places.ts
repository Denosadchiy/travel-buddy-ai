import { apiFetch, getPhotoUrl } from './client'
import type { PlaceDetailsResponse, PlacePhotoResponse } from '../types/api'

export function getPlacePhotoUrl(photoRef: string, maxWidth = 1200): string {
  return getPhotoUrl(photoRef, maxWidth)
}

export function getPlaceDetails(placeId: string): Promise<PlaceDetailsResponse> {
  return apiFetch(`/api/places/${encodeURIComponent(placeId)}/details`)
}

function scorePhoto(photo: PlacePhotoResponse): number {
  const width = photo.width || 0
  const height = photo.height || 0
  const area = width * height
  const ratio = height > 0 ? width / height : 1.3
  const ratioPenalty = Math.abs(ratio - 1.35) * 250000

  return area - ratioPenalty
}

export function pickBestPlacePhoto(photos: PlacePhotoResponse[]): PlacePhotoResponse | null {
  if (!photos.length) return null

  return [...photos].sort((a, b) => scorePhoto(b) - scorePhoto(a))[0] ?? null
}

export async function getBestPlacePhotoUrl(
  placeId: string,
  maxWidth = 1200
): Promise<string | null> {
  const details = await getPlaceDetails(placeId)
  const bestPhoto = pickBestPlacePhoto(details.photos)

  return bestPhoto ? getPhotoUrl(bestPhoto.id, maxWidth) : null
}
