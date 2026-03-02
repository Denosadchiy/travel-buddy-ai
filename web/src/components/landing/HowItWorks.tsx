import { MapPin, Sparkles, Map } from 'lucide-react'

const STEPS = [
  {
    number: 1,
    icon: MapPin,
    title: 'Choose Your Destination',
    description: 'Simply enter your destination and travel dates. Tell us your interests, budget, and pace.',
  },
  {
    number: 2,
    icon: Sparkles,
    title: 'AI Builds Your Route',
    description: 'Our advanced neural engine crafts a seamless, optimized journey connecting the best spots.',
  },
  {
    number: 3,
    icon: Map,
    title: 'Explore & Customize',
    description: 'Fine-tune your schedule with real-time data, drag-and-drop activities, and live maps.',
  },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">How It Works</h2>
          <p className="text-text-secondary text-lg max-w-2xl mx-auto">
            Seamless intelligence tailored to your travel desires.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {STEPS.map((step) => (
            <div
              key={step.number}
              className="relative bg-surface border border-border-default rounded-2xl p-8 hover:bg-surface-hover transition-colors group"
            >
              {/* Number badge */}
              <div className="absolute top-6 right-6 w-8 h-8 bg-primary/15 text-primary rounded-full flex items-center justify-center text-sm font-bold">
                {step.number}
              </div>

              <step.icon className="w-10 h-10 text-primary mb-6" strokeWidth={1.5} />

              <h3 className="text-xl font-semibold mb-3">{step.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
