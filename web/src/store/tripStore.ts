import { create } from 'zustand'
import type { TripCreateRequest, TripResponse, ItineraryResponse } from '../types/api'

interface TripFormState {
  city: string
  startDate: string
  endDate: string
  numTravelers: number
  pace: 'slow' | 'medium' | 'fast'
  budget: 'low' | 'medium' | 'high'
  interests: string[]
  additionalPreferences: string
}

interface TripStore {
  form: TripFormState
  trip: TripResponse | null
  itinerary: ItineraryResponse | null

  updateForm: (partial: Partial<TripFormState>) => void
  toggleInterest: (interest: string) => void
  setTrip: (trip: TripResponse) => void
  setItinerary: (itinerary: ItineraryResponse) => void
  resetForm: () => void

  toCreateRequest: () => TripCreateRequest
}

const initialForm: TripFormState = {
  city: '',
  startDate: '',
  endDate: '',
  numTravelers: 2,
  pace: 'medium',
  budget: 'medium',
  interests: [],
  additionalPreferences: '',
}

export const useTripStore = create<TripStore>((set, get) => ({
  form: { ...initialForm },
  trip: null,
  itinerary: null,

  updateForm: (partial) =>
    set((state) => ({ form: { ...state.form, ...partial } })),

  toggleInterest: (interest) =>
    set((state) => {
      const interests = state.form.interests.includes(interest)
        ? state.form.interests.filter((i) => i !== interest)
        : [...state.form.interests, interest]
      return { form: { ...state.form, interests } }
    }),

  setTrip: (trip) => set({ trip }),
  setItinerary: (itinerary) => set({ itinerary }),

  resetForm: () => set({ form: { ...initialForm }, trip: null, itinerary: null }),

  toCreateRequest: () => {
    const { form } = get()
    const req: TripCreateRequest = {
      city: form.city,
      start_date: form.startDate,
      end_date: form.endDate,
      num_travelers: form.numTravelers,
      pace: form.pace,
      budget: form.budget,
      interests: form.interests,
    }
    if (form.additionalPreferences.trim()) {
      req.additional_preferences = { notes: form.additionalPreferences.trim() }
    }
    return req
  },
}))
