import { useState, useRef, useEffect } from 'react'
import { Search } from 'lucide-react'

const POPULAR_CITIES = [
  'Paris', 'Rome', 'Barcelona', 'Istanbul', 'London', 'Amsterdam', 'Prague',
  'Vienna', 'Berlin', 'Lisbon', 'Athens', 'Budapest', 'Dublin', 'Florence',
  'Venice', 'Madrid', 'Munich', 'Zurich', 'Copenhagen', 'Stockholm',
  'Tokyo', 'Kyoto', 'Seoul', 'Bangkok', 'Singapore', 'Bali', 'Dubai',
  'New York', 'Los Angeles', 'San Francisco', 'Miami', 'Chicago',
  'Mexico City', 'Buenos Aires', 'Rio de Janeiro', 'Lima',
  'Sydney', 'Melbourne', 'Cape Town', 'Marrakech', 'Cairo',
  'Moscow', 'Saint Petersburg', 'Tbilisi', 'Yerevan',
]

interface Props {
  value: string
  onChange: (value: string) => void
}

export default function CityAutocomplete({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const filtered = value.length > 0
    ? POPULAR_CITIES.filter((city) =>
        city.toLowerCase().startsWith(value.toLowerCase())
      )
    : POPULAR_CITIES.slice(0, 8)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <label className="block text-sm text-text-secondary mb-2">Destination</label>
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder="Where do you want to go? (e.g., Tokyo, Paris)"
          className="w-full bg-surface border border-border-default rounded-xl pl-11 pr-4 py-3.5 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
        />
      </div>

      {open && filtered.length > 0 && (
        <div className="absolute z-20 top-full mt-1 w-full bg-[#1a1a1d] border border-border-default rounded-xl shadow-xl max-h-60 overflow-y-auto">
          {filtered.map((city) => (
            <button
              key={city}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange(city)
                setOpen(false)
              }}
              className="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:text-white hover:bg-surface-hover transition-colors first:rounded-t-xl last:rounded-b-xl"
            >
              {city}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
