import { Brain, Route, Star, Map, CalendarDays, BedDouble } from 'lucide-react'

const FEATURES = [
  {
    icon: Brain,
    title: 'AI-Powered Planning',
    description: 'Context-aware planning that learns from millions of data points to suggest the perfect trip.',
  },
  {
    icon: Route,
    title: 'Walking Routes',
    description: 'Optimized pedestrian paths between landmarks to ensure you see the city at the right pace.',
  },
  {
    icon: Star,
    title: 'Real Places & Ratings',
    description: 'Live integration with real-world ratings ensuring you only visit high-quality venues.',
  },
  {
    icon: BedDouble,
    title: 'Accommodation Booking',
    description: 'Find and book the perfect stay near your itinerary. Integrated with top booking platforms.',
  },
  {
    icon: CalendarDays,
    title: 'Day-by-Day Schedule',
    description: 'Structured chronologies that balance activity with relaxation, tailored to your energy.',
  },
  {
    icon: Map,
    title: 'Interactive Map',
    description: 'Visualize your entire journey on a fluid, custom-designed interface with live updates.',
  },
]

export default function FeaturesSection() {
  return (
    <section id="features" className="py-24">
      <div className="max-w-7xl mx-auto px-6">
        <div className="mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">Exceptional Capabilities</h2>
          <p className="text-text-secondary text-lg">
            Designed for the modern traveler who demands precision.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="bg-surface border border-border-default rounded-2xl p-7 hover:bg-surface-hover hover:border-white/12 transition-all group"
            >
              <div className="w-11 h-11 bg-primary/12 rounded-xl flex items-center justify-center mb-5">
                <feature.icon className="w-5 h-5 text-primary" strokeWidth={1.5} />
              </div>
              <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
