import { Pencil, Footprints, BedDouble } from 'lucide-react'
import type { ItineraryDay } from '../../types/api'
import ActivityItem from './ActivityItem'
import { formatDistance } from '../../lib/utils'
import { getChronologicalPoiBlocks } from '../../lib/itinerary'

interface Props {
  day: ItineraryDay
}

export default function DayCard({ day }: Props) {
  const activities = getChronologicalPoiBlocks(day)
  const totalDistance = day.blocks.reduce(
    (sum, b) => sum + (b.travel_distance_meters || 0),
    0
  )

  return (
    <div className="bg-surface border border-border-default rounded-2xl p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-primary/15 text-primary rounded-full flex items-center justify-center text-sm font-bold">
            {String(day.day_number).padStart(2, '0')}
          </div>
          <div>
            <h3 className="text-lg font-semibold">
              Day {day.day_number}: {day.theme}
            </h3>
            <div className="flex items-center gap-4 text-text-muted text-sm mt-0.5">
              <span className="flex items-center gap-1">
                {activities.length} activities
              </span>
              <span className="flex items-center gap-1">
                <Footprints size={13} />
                {formatDistance(totalDistance)}
              </span>
            </div>
          </div>
        </div>

        <button className="flex items-center gap-1.5 text-text-secondary hover:text-white text-sm border border-border-default rounded-lg px-3 py-1.5 hover:bg-surface-hover transition-colors">
          Edit Day
          <Pencil size={13} />
        </button>
      </div>

      {/* Activity timeline */}
      <div className="space-y-0.5">
        {activities.map((block, idx) => (
          <ActivityItem
            key={block.poi!.poi_id}
            block={block}
            isFirst={idx === 0}
            isLast={idx === activities.length - 1}
            index={idx}
            dayTheme={day.theme}
          />
        ))}
      </div>

      {/* Book Accommodation CTA */}
      {day.day_number === 1 && (
        <div className="mt-4 pt-4 border-t border-border-default">
          <button className="w-full flex items-center justify-center gap-2 text-sm font-medium text-primary hover:text-white bg-primary/8 hover:bg-primary/15 border border-primary/20 rounded-xl py-3 transition-colors">
            <BedDouble size={16} />
            Find Accommodation for This Trip
          </button>
        </div>
      )}
    </div>
  )
}
