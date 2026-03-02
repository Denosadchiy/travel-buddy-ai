import { Coffee, Footprints, Zap } from 'lucide-react'
import clsx from 'clsx'

const ICONS: Record<string, React.ElementType> = { Coffee, Footprints, Zap }

const OPTIONS = [
  { value: 'slow', label: 'Relaxed', subtitle: 'Take it slow', icon: 'Coffee' },
  { value: 'medium', label: 'Moderate', subtitle: 'See the main sights', icon: 'Footprints' },
  { value: 'fast', label: 'Active', subtitle: 'Packed schedule', icon: 'Zap' },
] as const

interface Props {
  value: string
  onChange: (value: 'slow' | 'medium' | 'fast') => void
}

export default function PaceSelector({ value, onChange }: Props) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-3">Travel Pace</label>
      <div className="grid grid-cols-3 gap-3">
        {OPTIONS.map((opt) => {
          const Icon = ICONS[opt.icon]
          const isSelected = value === opt.value
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              className={clsx(
                'flex flex-col items-center gap-2 p-5 rounded-xl border transition-all',
                isSelected
                  ? 'bg-surface-selected border-primary'
                  : 'bg-surface border-border-default hover:bg-surface-hover'
              )}
            >
              <Icon size={22} className={isSelected ? 'text-primary' : 'text-text-muted'} />
              <span className={clsx('text-sm font-semibold', isSelected ? 'text-white' : 'text-text-secondary')}>
                {opt.label}
              </span>
              <span className="text-xs text-text-muted">{opt.subtitle}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
