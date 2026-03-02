import { Bookmark } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

interface Props {
  onSave: () => void
  isSaved: boolean
}

export default function SaveTripButton({ onSave, isSaved }: Props) {
  const { isAuthenticated, openLoginModal } = useAuthStore()

  const handleClick = () => {
    if (!isAuthenticated) {
      openLoginModal()
      return
    }
    onSave()
  }

  return (
    <div className="px-6 py-6">
      <button
        onClick={handleClick}
        disabled={isSaved}
        className="w-full max-w-md mx-auto flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:bg-primary/50 text-white font-semibold py-4 rounded-xl text-lg transition-colors"
      >
        <Bookmark size={20} />
        {isSaved ? 'Trip Saved' : 'Save Trip'}
      </button>
    </div>
  )
}
