import { CalendarDays, Route, MapPin, DollarSign } from 'lucide-react'
import type { ItineraryResponse } from '../../types/api'
import { formatDistance } from '../../lib/utils'

interface Props {
  itinerary: ItineraryResponse
  budget?: string
}

export default function StatsRow({ itinerary, budget }: Props) {
  const totalDays = itinerary.days.length
  const totalPois = itinerary.days.reduce(
    (sum, day) => sum + day.blocks.filter((b) => b.poi).length,
    0
  )
  const totalDistance = itinerary.days.reduce(
    (sum, day) =>
      sum +
      day.blocks.reduce((s, b) => s + (b.travel_distance_meters || 0), 0),
    0
  )

  const dailyCost = budget === 'high' ? 250 : budget === 'medium' ? 120 : 60
  const estimatedCost = `~$${dailyCost * totalDays}`

  const stats = [
    { icon: CalendarDays, value: `${totalDays} Days`, label: 'DURATION' },
    { icon: Route, value: formatDistance(totalDistance), label: 'DISTANCE' },
    { icon: MapPin, value: `${totalPois} Places`, label: 'STOPS' },
    { icon: DollarSign, value: estimatedCost, label: 'EST. COST' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-6">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="bg-surface border border-border-default rounded-xl p-4 text-center"
        >
          <stat.icon className="w-5 h-5 text-primary mx-auto mb-2" />
          <p className="text-white font-bold text-lg">{stat.value}</p>
          <p className="text-text-muted text-xs uppercase tracking-wider mt-0.5">{stat.label}</p>
        </div>
      ))}
    </div>
  )
}
