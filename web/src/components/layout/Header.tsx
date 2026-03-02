import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import UserMenu from '../auth/UserMenu'

const LANDING_NAV = [
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Features', href: '#features' },
  { label: 'About', href: '#about' },
  { label: 'Contact', href: '#contact' },
]

const APP_NAV = [
  { label: 'Explore', href: '/' },
  { label: 'My Trips', href: '/trips' },
  { label: 'Plan Trip', href: '/plan' },
]

export default function Header() {
  const location = useLocation()
  const isLanding = location.pathname === '/'
  const nav = isLanding ? LANDING_NAV : APP_NAV
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { isAuthenticated, openLoginModal } = useAuthStore()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'bg-base/80 backdrop-blur-md border-b border-white/5' : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center no-underline">
          <img src="/logo-wordmark.svg" alt="Locally" className="h-10 w-auto" />
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          {nav.map((item) =>
            item.href.startsWith('#') ? (
              <a
                key={item.label}
                href={item.href}
                className="text-text-secondary hover:text-white transition-colors text-sm no-underline"
              >
                {item.label}
              </a>
            ) : (
              <Link
                key={item.label}
                to={item.href}
                className="text-text-secondary hover:text-white transition-colors text-sm no-underline"
              >
                {item.label}
              </Link>
            )
          )}
        </nav>

        {/* Right Actions */}
        <div className="hidden md:flex items-center gap-4">
          {isAuthenticated ? (
            <UserMenu />
          ) : (
            <button
              onClick={openLoginModal}
              className="text-text-secondary hover:text-white transition-colors text-sm"
            >
              Sign In
            </button>
          )}
          <Link
            to="/plan"
            className="bg-primary hover:bg-primary-hover text-white text-sm font-semibold px-5 py-2.5 rounded-full transition-colors no-underline"
          >
            Plan Your Trip
          </Link>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden text-white p-2"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="md:hidden bg-base/95 backdrop-blur-md border-t border-white/5 px-6 py-4 space-y-4">
          {nav.map((item) =>
            item.href.startsWith('#') ? (
              <a
                key={item.label}
                href={item.href}
                className="block text-text-secondary hover:text-white transition-colors no-underline"
                onClick={() => setMobileOpen(false)}
              >
                {item.label}
              </a>
            ) : (
              <Link
                key={item.label}
                to={item.href}
                className="block text-text-secondary hover:text-white transition-colors no-underline"
                onClick={() => setMobileOpen(false)}
              >
                {item.label}
              </Link>
            )
          )}
          <div className="pt-4 border-t border-white/5 space-y-3">
            {isAuthenticated ? (
              <UserMenu />
            ) : (
              <button
                onClick={() => { openLoginModal(); setMobileOpen(false) }}
                className="block text-text-secondary hover:text-white transition-colors"
              >
                Sign In
              </button>
            )}
            <Link
              to="/plan"
              className="block bg-primary text-white text-center font-semibold px-5 py-2.5 rounded-full no-underline"
              onClick={() => setMobileOpen(false)}
            >
              Plan Your Trip
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
