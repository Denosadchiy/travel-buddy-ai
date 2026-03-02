import { Wallet, Star, Diamond } from 'lucide-react'
import clsx from 'clsx'

const ICONS: Record<string, React.ElementType> = { Wallet, Star, Diamond }

const OPTIONS = [
  { value: 'low', label: 'Budget', subtitle: 'Cost effective', icon: 'Wallet' },
  { value: 'medium', label: 'Comfort', subtitle: 'Balanced spend', icon: 'Star' },
  { value: 'high', label: 'Premium', subtitle: 'Luxury experience', icon: 'Diamond' },
] as const

interface Props {
  value: string
  onChange: (value: 'low' | 'medium' | 'high') => void
}

export default function BudgetSelector({ value, onChange }: Props) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-3">Budget Preference</label>
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
