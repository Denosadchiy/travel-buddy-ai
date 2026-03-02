import { apiFetch } from './client'
import type { SavedTripResponse } from '../types/api'

export function getSavedTrips(limit?: number): Promise<SavedTripResponse[]> {
  const params = limit ? `?limit=${limit}` : ''
  return apiFetch(`/api/saved_trips${params}`)
}

export function saveTrip(data: {
  trip_id: string
  city_name: string
  start_date: string
  end_date: string
  hero_image_url?: string
}): Promise<SavedTripResponse> {
  return apiFetch('/api/saved_trips', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteSavedTrip(savedTripId: string): Promise<void> {
  return apiFetch(`/api/saved_trips/${savedTripId}`, {
    method: 'DELETE',
  })
}
