import { useState } from 'react'
import { ArrowLeft, Share2, Check, CalendarDays, Users, Bookmark } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { getPhotoUrl } from '../../api/client'
import { formatDateRange } from '../../lib/utils'

interface Props {
  cityName: string
  photoRef: string | null
  startDate: string
  endDate: string
  numTravelers: number
  onSave?: () => void
  isSaved?: boolean
}

export default function HeroImage({ cityName, photoRef, startDate, endDate, numTravelers, onSave, isSaved }: Props) {
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)
  const bgImage = photoRef ? getPhotoUrl(photoRef, 1600) : undefined

  const handleShare = async () => {
    const url = window.location.href
    if (navigator.share) {
      try {
        await navigator.share({ title: `Trip to ${cityName}`, url })
      } catch { /* user cancelled */ }
    } else {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="relative w-full overflow-hidden" style={{ height: 'clamp(320px, 45vh, 480px)' }}>
      {/* Background */}
      {bgImage ? (
        <img
          src={bgImage}
          alt={cityName}
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-primary/30 via-base to-base" />
      )}

      {/* Gradient overlays */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/20 to-base" />

      {/* Top buttons */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-center z-10">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 rounded-full bg-black/30 backdrop-blur-md flex items-center justify-center text-white hover:bg-black/50 transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex items-center gap-2">
          {onSave && (
            <button
              onClick={onSave}
              disabled={isSaved}
              className="w-10 h-10 rounded-full bg-black/30 backdrop-blur-md flex items-center justify-center text-white hover:bg-black/50 transition-colors disabled:opacity-60"
            >
              <Bookmark size={18} fill={isSaved ? 'currentColor' : 'none'} />
            </button>
          )}
          <button
            onClick={handleShare}
            className="w-10 h-10 rounded-full bg-black/30 backdrop-blur-md flex items-center justify-center text-white hover:bg-black/50 transition-colors"
          >
            {copied ? <Check size={18} /> : <Share2 size={18} />}
          </button>
        </div>
      </div>

      {/* Bottom content */}
      <div className="absolute bottom-0 left-0 right-0 p-6 z-10">
        <h1 className="text-4xl sm:text-5xl font-bold text-white drop-shadow-lg tracking-tight">
          {cityName}
        </h1>
        <div className="flex items-center gap-4 mt-3">
          <span className="flex items-center gap-1.5 text-white/80 text-sm">
            <CalendarDays size={14} />
            {formatDateRange(startDate, endDate)}
          </span>
          <span className="flex items-center gap-1.5 text-white/80 text-sm">
            <Users size={14} />
            {numTravelers} {numTravelers === 1 ? 'traveler' : 'travelers'}
          </span>
        </div>
      </div>
    </div>
  )
}
