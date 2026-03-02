import { useState, useCallback, useEffect, useRef } from 'react'
import { APIProvider, Map, AdvancedMarker, InfoWindow, useMap } from '@vis.gl/react-google-maps'
import { Star, MapPin } from 'lucide-react'
import type { ItineraryDay, POI } from '../../types/api'
import { CATEGORY_COLORS } from '../../lib/constants'
import { formatTime } from '../../lib/utils'
import { getChronologicalPoiBlocks } from '../../lib/itinerary'
import { usePlaceInsights } from '../../hooks/usePlaceInsights'
import { getPlaceAbout, getPlaceWhy } from '../../lib/placeNarrative'

interface Props {
  day: ItineraryDay
  highlightedPoi?: string | null
  onMarkerClick?: (poiId: string) => void
}

const MAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
const MAP_ID = 'locally-dark-map'
const CATEGORY_ICONS: Record<string, string> = {
  restaurant: '🍽️',
  food: '🍽️',
  meal: '🍽️',
  cafe: '☕',
  museum: '🏛️',
  culture: '🏛️',
  park: '🌳',
  attraction: '📸',
  activity: '📸',
  viewpoint: '🌅',
  nightlife: '🍸',
  shopping: '🛍️',
  rest: '☕',
}

/**
 * Requests shortest walking directions between consecutive POIs
 * using the Google Maps Directions Service, then draws the result.
 */
function useDirectionsRoutes(day: ItineraryDay) {
  const map = useMap()
  const renderersRef = useRef<google.maps.DirectionsRenderer[]>([])
  const routeBlocks = getChronologicalPoiBlocks(day)
  const routeKey = routeBlocks
    .map((block) => `${block.poi?.poi_id ?? 'unknown'}:${block.start_time}`)
    .join('|')

  useEffect(() => {
    // Cleanup previous renderers
    renderersRef.current.forEach((r) => r.setMap(null))
    renderersRef.current = []

    if (!map) return

    const pois = routeBlocks.map((b) => b.poi!)
    if (pois.length < 2) return

    const service = new google.maps.DirectionsService()

    // Request directions for each consecutive pair
    for (let i = 0; i < pois.length - 1; i++) {
      const origin = { lat: pois[i].lat, lng: pois[i].lon }
      const dest = { lat: pois[i + 1].lat, lng: pois[i + 1].lon }

      service.route(
        {
          origin,
          destination: dest,
          travelMode: google.maps.TravelMode.WALKING,
          provideRouteAlternatives: false,
        },
        (result, status) => {
          if (status !== google.maps.DirectionsStatus.OK || !result) return

          const renderer = new google.maps.DirectionsRenderer({
            map,
            directions: result,
            suppressMarkers: true,
            preserveViewport: true,
            polylineOptions: {
              strokeColor: '#f76b2e',
              strokeOpacity: 0.85,
              strokeWeight: 4,
            },
          })
          renderersRef.current.push(renderer)
        }
      )
    }

    return () => {
      renderersRef.current.forEach((r) => r.setMap(null))
      renderersRef.current = []
    }
  }, [map, routeBlocks, routeKey])
}

function MapContent({ day, highlightedPoi, onMarkerClick }: Props) {
  const map = useMap()
  const blocks = getChronologicalPoiBlocks(day)
  const pois = blocks.map((b) => ({ poi: b.poi!, time: b.start_time }))
  const boundsKey = pois.map(({ poi, time }) => `${poi.poi_id}:${time}`).join('|')
  const [selectedPoi, setSelectedPoi] = useState<{ poi: POI; time: string } | null>(null)
  const { details, photoUrl, isLoading } = usePlaceInsights(selectedPoi?.poi.poi_id, 720)
  const selectedBlock = selectedPoi
    ? blocks.find((block) => block.poi?.poi_id === selectedPoi.poi.poi_id) ?? null
    : null

  // Draw walking routes between consecutive POIs
  useDirectionsRoutes(day)

  // Fit bounds to show all markers
  useEffect(() => {
    if (!map || pois.length === 0) return
    if (pois.length === 1) {
      map.setCenter({ lat: pois[0].poi.lat, lng: pois[0].poi.lon })
      map.setZoom(15)
      return
    }
    let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity
    pois.forEach(({ poi }) => {
      if (poi.lat < minLat) minLat = poi.lat
      if (poi.lat > maxLat) maxLat = poi.lat
      if (poi.lon < minLng) minLng = poi.lon
      if (poi.lon > maxLng) maxLng = poi.lon
    })
    const pad = 0.005
    map.fitBounds({
      north: maxLat + pad,
      south: minLat - pad,
      east: maxLng + pad,
      west: minLng - pad,
    })
  }, [boundsKey, map])

  // Sync highlighted POI from timeline
  useEffect(() => {
    if (highlightedPoi) {
      const found = pois.find((p) => p.poi.poi_id === highlightedPoi)
      if (found) setSelectedPoi(found)
    }
  }, [highlightedPoi])

  const handleMarkerClick = useCallback((poi: POI, time: string) => {
    setSelectedPoi({ poi, time })
    onMarkerClick?.(poi.poi_id)
    map?.panTo({ lat: poi.lat, lng: poi.lon })
  }, [map, onMarkerClick])

  return (
    <>
      {/* POI markers */}
      {pois.map(({ poi, time }, idx) => {
        const color = CATEGORY_COLORS[poi.category] || CATEGORY_COLORS[blocks[idx]?.block_type || ''] || '#f76b2e'
        const isSelected = selectedPoi?.poi.poi_id === poi.poi_id

        return (
          <AdvancedMarker
            key={poi.poi_id}
            position={{ lat: poi.lat, lng: poi.lon }}
            onClick={() => handleMarkerClick(poi, time)}
            zIndex={isSelected ? 10 : idx + 1}
          >
            <div
              className="flex items-center justify-center rounded-full text-white text-xs font-bold shadow-lg transition-transform"
              style={{
                width: isSelected ? 36 : 28,
                height: isSelected ? 36 : 28,
                backgroundColor: color,
                border: isSelected ? '3px solid white' : '2px solid rgba(255,255,255,0.5)',
                transform: isSelected ? 'scale(1.1)' : 'scale(1)',
              }}
            >
              {idx + 1}
            </div>
          </AdvancedMarker>
        )
      })}

      {/* Info window */}
      {selectedPoi && (
        <InfoWindow
          position={{ lat: selectedPoi.poi.lat, lng: selectedPoi.poi.lon }}
          onCloseClick={() => setSelectedPoi(null)}
          pixelOffset={[0, -20]}
        >
          <div className="p-1 max-w-[240px]">
            <div className="relative w-full h-28 rounded-lg overflow-hidden mb-2 bg-gray-100">
              {photoUrl ? (
                <img
                  src={photoUrl}
                  alt={selectedPoi.poi.name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div
                  className="w-full h-full flex items-center justify-center text-3xl"
                  style={{
                    background: isLoading
                      ? 'linear-gradient(135deg, rgba(247,107,46,0.16), rgba(17,24,39,0.08))'
                      : 'linear-gradient(135deg, rgba(247,107,46,0.14), rgba(17,24,39,0.10))',
                  }}
                >
                  {CATEGORY_ICONS[selectedPoi.poi.category] || '📍'}
                </div>
              )}
              <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black/35 to-transparent pointer-events-none" />
            </div>
            <p className="font-semibold text-sm text-gray-900">{selectedPoi.poi.name}</p>
            <div className="flex items-center gap-2 mt-1 text-gray-600 text-xs">
              <span>{formatTime(selectedPoi.time)}</span>
              {selectedPoi.poi.rating && (
                <span className="flex items-center gap-0.5">
                  <Star size={10} fill="#eab308" stroke="#eab308" />
                {selectedPoi.poi.rating}
                </span>
              )}
            </div>
            {selectedBlock && (
              <>
                <p className="text-[11px] leading-relaxed text-gray-700 mt-2">
                  {getPlaceWhy(selectedBlock, day.theme, details)}
                </p>
                <p className="text-[11px] leading-relaxed text-gray-500 mt-1">
                  {getPlaceAbout(selectedBlock, details)}
                </p>
              </>
            )}
            {selectedPoi.poi.location && (
              <p className="text-gray-500 text-xs mt-1 flex items-center gap-1">
                <MapPin size={10} />
                {selectedPoi.poi.location}
              </p>
            )}
          </div>
        </InfoWindow>
      )}
    </>
  )
}

export default function RouteMap({ day, highlightedPoi, onMarkerClick }: Props) {
  const pois = getChronologicalPoiBlocks(day).map((b) => b.poi!)

  if (pois.length === 0 || !MAPS_KEY) return null

  const center = { lat: pois[0].lat, lng: pois[0].lon }

  return (
    <APIProvider apiKey={MAPS_KEY}>
      <Map
        defaultCenter={center}
        defaultZoom={13}
        mapId={MAP_ID}
        gestureHandling="greedy"
        disableDefaultUI={false}
        zoomControl={true}
        mapTypeControl={false}
        streetViewControl={false}
        fullscreenControl={true}
        className="w-full h-full rounded-xl"
        colorScheme="DARK"
      >
        <MapContent
          day={day}
          highlightedPoi={highlightedPoi}
          onMarkerClick={onMarkerClick}
        />
      </Map>
    </APIProvider>
  )
}
