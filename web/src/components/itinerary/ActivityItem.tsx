import { useState } from 'react'
import { Star, Clock, MapPin, ChevronDown, ChevronUp, Navigation } from 'lucide-react'
import type { ActivityBlock } from '../../types/api'
import { CATEGORY_COLORS } from '../../lib/constants'
import { formatTime } from '../../lib/utils'
import { usePlaceInsights } from '../../hooks/usePlaceInsights'
import { getPlaceAbout, getPlaceWhy } from '../../lib/placeNarrative'

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

interface Props {
  block: ActivityBlock
  isFirst: boolean
  isLast: boolean
  index: number
  dayTheme?: string
}

export default function ActivityItem({ block, isFirst, isLast, index, dayTheme }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (!block.poi) return null

  const poi = block.poi
  const color = CATEGORY_COLORS[block.block_type] || CATEGORY_COLORS[poi.category] || '#8E8E93'
  const emoji = CATEGORY_ICONS[poi.category] || CATEGORY_ICONS[block.block_type] || '📍'
  const { details, photoUrl, isLoading } = usePlaceInsights(poi.poi_id, 720)
  const whyText = getPlaceWhy(block, dayTheme, details)
  const aboutText = getPlaceAbout(block, details)

  return (
    <div className="flex gap-3">
      {/* Timeline */}
      <div className="flex flex-col items-center w-6 shrink-0">
        {!isFirst && <div className="w-px flex-1 bg-white/10" />}
        <div
          className="w-6 h-6 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold"
          style={{ backgroundColor: color }}
        >
          {index + 1}
        </div>
        {!isLast && <div className="w-px flex-1 bg-white/10" />}
      </div>

      {/* Card */}
      <div
        className="flex-1 bg-surface border border-border-default rounded-xl mb-2 overflow-hidden cursor-pointer hover:border-white/15 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex">
          {/* Thumbnail */}
          <div className="w-20 h-20 sm:w-24 sm:h-24 shrink-0 relative overflow-hidden">
            {photoUrl ? (
              <img
                src={photoUrl}
                alt={poi.name}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            ) : (
              <div
                className="w-full h-full flex items-center justify-center text-2xl transition-opacity"
                style={{
                  background: isLoading
                    ? `linear-gradient(135deg, ${color}18, rgba(255,255,255,0.08))`
                    : `${color}20`,
                  opacity: isLoading ? 0.85 : 1,
                }}
              >
                {emoji}
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-black/25 to-transparent pointer-events-none" />
          </div>

          {/* Info */}
          <div className="flex-1 p-3 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-white font-semibold text-sm truncate">{poi.name}</p>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className="flex items-center gap-1 text-text-muted text-xs">
                    <Clock size={11} />
                    {formatTime(block.start_time)}
                  </span>
                  {poi.rating && (
                    <span className="flex items-center gap-0.5 text-yellow-400 text-xs">
                      <Star size={11} fill="currentColor" />
                      {poi.rating}
                    </span>
                  )}
                  <span
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                    style={{ color, background: `${color}20` }}
                  >
                    {poi.category}
                  </span>
                </div>
              </div>
              <button className="text-text-muted shrink-0 mt-0.5">
                {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>

            {!expanded && (
              <div className="mt-1.5 space-y-1">
                <p className="text-text-secondary text-[11px] leading-relaxed line-clamp-2">
                  {whyText}
                </p>
                <p className="text-text-muted text-[11px] leading-relaxed line-clamp-1">
                  {aboutText}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Expanded details */}
        {expanded && (
          <div className="px-3 pb-3 space-y-2 border-t border-border-default pt-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-primary/80 mb-1">
                Why this stop
              </p>
              <p className="text-text-secondary text-xs leading-relaxed">{whyText}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/55 mb-1">
                About this place
              </p>
              <p className="text-text-secondary text-xs leading-relaxed">{aboutText}</p>
            </div>
            <div className="flex items-center gap-1.5 text-text-muted text-xs">
              <MapPin size={11} />
              <span>{poi.location}</span>
            </div>
            <a
              href={`https://www.google.com/maps/dir/?api=1&destination=${poi.lat},${poi.lon}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1.5 text-primary text-xs font-medium hover:underline"
            >
              <Navigation size={11} />
              Open in Google Maps
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
