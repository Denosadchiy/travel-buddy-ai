interface Props {
  value: string
  onChange: (value: string) => void
}

export default function PreferencesTextarea({ value, onChange }: Props) {
  return (
    <div>
      <label className="block text-sm text-text-secondary mb-2">Special Requests or Notes</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        placeholder="Anything else we should know? (e.g., Dietary restrictions, specific landmarks...)"
        className="w-full bg-surface border border-border-default rounded-xl px-4 py-3.5 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors resize-none"
      />
    </div>
  )
}
