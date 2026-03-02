import { useState, useRef, useEffect } from 'react'
import { LogOut } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

export default function UserMenu() {
  const { user, logout } = useAuthStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (!user) return null

  const initials = (user.display_name || user.email || 'U')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-9 h-9 rounded-full bg-primary/20 text-primary font-semibold text-sm flex items-center justify-center hover:bg-primary/30 transition-colors"
      >
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
        ) : (
          initials
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-12 w-56 bg-base/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl py-2 z-50">
          <div className="px-4 py-3 border-b border-white/5">
            <p className="text-sm font-medium truncate">{user.display_name || 'User'}</p>
            <p className="text-xs text-text-muted truncate">{user.email}</p>
          </div>
          <button
            onClick={() => {
              logout()
              setOpen(false)
            }}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-text-secondary hover:text-white hover:bg-white/5 transition-colors"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </div>
      )}
    </div>
  )
}
