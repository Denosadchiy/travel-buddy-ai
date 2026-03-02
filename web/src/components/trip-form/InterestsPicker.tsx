import { UtensilsCrossed, Landmark, Wine, Compass, Sparkles, ShoppingBag } from 'lucide-react'
import clsx from 'clsx'

const ICONS: Record<string, React.ElementType> = {
  UtensilsCrossed,
  Landmark,
  Wine,
  Compass,
  Sparkles,
  ShoppingBag,
}

const INTERESTS = [
  { id: 'food', label: 'Food & Dining', icon: 'UtensilsCrossed' },
  { id: 'culture', label: 'Culture', icon: 'Landmark' },
  { id: 'nightlife', label: 'Nightlife', icon: 'Wine' },
  { id: 'adventure', label: 'Adventure', icon: 'Compass' },
  { id: 'relaxation', label: 'Relaxation', icon: 'Sparkles' },
  { id: 'shopping', label: 'Shopping', icon: 'ShoppingBag' },
]

interface Props {
  selected: string[]
  onToggle: (id: string) => void
}

export default function InterestsPicker({ selected, onToggle }: Props) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-3">Your Interests</label>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {INTERESTS.map((interest) => {
          const Icon = ICONS[interest.icon]
          const isSelected = selected.includes(interest.id)
          return (
            <button
              key={interest.id}
              type="button"
              onClick={() => onToggle(interest.id)}
              className={clsx(
                'flex items-center justify-center gap-2.5 px-4 py-3.5 rounded-xl border transition-all text-sm font-medium',
                isSelected
                  ? 'bg-surface-selected border-primary text-white'
                  : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover hover:text-white'
              )}
            >
              <Icon size={16} />
              {interest.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
