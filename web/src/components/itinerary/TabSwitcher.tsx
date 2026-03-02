import clsx from 'clsx'

export type TabId = 'route' | 'overview'

interface Props {
  activeTab: TabId
  onChange: (tab: TabId) => void
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'route', label: 'Route' },
  { id: 'overview', label: 'Overview' },
]

export default function TabSwitcher({ activeTab, onChange }: Props) {
  return (
    <div className="inline-flex gap-1 bg-surface rounded-full p-1">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            'px-5 py-2 rounded-full text-sm font-medium transition-all',
            activeTab === tab.id
              ? 'bg-primary text-white'
              : 'text-text-secondary hover:text-white'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
