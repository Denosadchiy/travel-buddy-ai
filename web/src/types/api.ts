// Trip creation
export interface TripCreateRequest {
  city: string
  start_date: string
  end_date: string
  num_travelers: number
  pace: 'slow' | 'medium' | 'fast'
  budget: 'low' | 'medium' | 'high'
  interests: string[]
  additional_preferences?: Record<string, string>
}

export interface TripResponse {
  id: string
  city: string
  city_center_lat: number
  city_center_lon: number
  start_date: string
  end_date: string
  num_travelers: number
  pace: string
  budget: string
  interests: string[]
  city_photo_reference: string | null
  created_at: string
}

// Itinerary
export interface ItineraryResponse {
  trip_id: string
  days: ItineraryDay[]
  is_locked: boolean
  created_at: string
  city_photo_reference: string | null
}

export interface ItineraryDay {
  day_number: number
  date: string
  theme: string
  blocks: ActivityBlock[]
}

export interface ActivityBlock {
  block_type: 'meal' | 'activity' | 'nightlife' | 'rest' | 'travel'
  start_time: string
  end_time: string
  poi: POI | null
  travel_time_from_prev: number | null
  travel_distance_meters: number | null
  travel_polyline: string | null
  notes: string | null
}

export interface POI {
  poi_id: string
  name: string
  category: string
  tags: string[]
  rating: number | null
  user_ratings_total: number | null
  location: string
  lat: number
  lon: number
  description: string | null
}

export interface PlacePhotoResponse {
  id: string
  width: number | null
  height: number | null
  attribution: string[]
}

export interface PlaceDetailsResponse {
  place_id: string
  name: string
  types: string[]
  rating: number | null
  reviews_count: number | null
  is_open_now: boolean | null
  address: string | null
  editorial_summary: string | null
  photos: PlacePhotoResponse[]
}

// Auth
export interface SessionResponse {
  access_token: string
  refresh_token: string
  token_type: 'Bearer'
  expires_in: number
  user: User
}

export interface EmailStartResponse {
  challenge_id: string
  message: string
  delivery_method: string
  debug_code: string | null
}

export interface User {
  id: string
  email: string | null
  display_name: string | null
  avatar_url: string | null
  created_at: string
}

// Saved trips
export interface SavedTripRequest {
  trip_id: string
  city_name: string
  start_date: string
  end_date: string
  hero_image_url?: string
}

export interface SavedTripResponse {
  id: string
  trip_id: string
  city_name: string
  start_date: string
  end_date: string
  hero_image_url: string | null
  already_saved?: boolean
}
