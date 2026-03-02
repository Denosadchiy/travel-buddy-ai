import { Calendar } from 'lucide-react'

interface Props {
  startDate: string
  endDate: string
  onStartChange: (value: string) => void
  onEndChange: (value: string) => void
}

export default function DateRangePicker({ startDate, endDate, onStartChange, onEndChange }: Props) {
  const today = new Date().toISOString().split('T')[0]

  return (
    <div>
      <label className="block text-sm text-text-secondary mb-2">Travel Dates</label>
      <div className="grid grid-cols-2 gap-3">
        <div className="relative">
          <Calendar className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
          <input
            type="date"
            value={startDate}
            min={today}
            onChange={(e) => onStartChange(e.target.value)}
            className="w-full bg-surface border border-border-default rounded-xl pl-11 pr-4 py-3.5 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]"
          />
        </div>
        <div className="relative">
          <Calendar className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
          <input
            type="date"
            value={endDate}
            min={startDate || today}
            onChange={(e) => onEndChange(e.target.value)}
            className="w-full bg-surface border border-border-default rounded-xl pl-11 pr-4 py-3.5 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]"
          />
        </div>
      </div>
    </div>
  )
}
