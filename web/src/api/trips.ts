import { apiFetch } from './client'
import type { TripCreateRequest, TripResponse, ItineraryResponse } from '../types/api'

export function createTrip(data: TripCreateRequest): Promise<TripResponse> {
  return apiFetch('/api/trips', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function generatePlan(tripId: string, signal?: AbortSignal): Promise<ItineraryResponse> {
  return apiFetch(`/api/trips/${tripId}/plan`, {
    method: 'POST',
    signal,
  })
}

export function getItinerary(tripId: string): Promise<ItineraryResponse> {
  return apiFetch(`/api/trips/${tripId}/itinerary`)
}

export function getTrip(tripId: string): Promise<TripResponse> {
  return apiFetch(`/api/trips/${tripId}`)
}
