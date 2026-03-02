import { Minus, Plus } from 'lucide-react'

interface Props {
  value: number
  onChange: (value: number) => void
}

export default function TravelersInput({ value, onChange }: Props) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-2">Number of Travelers</label>
      <div className="flex items-center bg-surface border border-border-default rounded-xl overflow-hidden">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, value - 1))}
          className="px-5 py-3.5 text-text-secondary hover:text-white hover:bg-white/5 transition-colors"
        >
          <Minus size={18} />
        </button>
        <span className="flex-1 text-center text-white font-medium">
          {value} {value === 1 ? 'Traveler' : 'Travelers'}
        </span>
        <button
          type="button"
          onClick={() => onChange(Math.min(20, value + 1))}
          className="px-5 py-3.5 text-text-secondary hover:text-white hover:bg-white/5 transition-colors"
        >
          <Plus size={18} />
        </button>
      </div>
    </div>
  )
}
