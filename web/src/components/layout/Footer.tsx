import { Link } from 'react-router-dom'

const PRODUCT_LINKS = [
  { label: 'How it Works', href: '/#how-it-works', isAnchor: true },
  { label: 'Features', href: '/#features', isAnchor: true },
  { label: 'Plan a Trip', href: '/plan', isAnchor: false },
]

const COMPANY_LINKS = [
  { label: 'About', href: '/about', isAnchor: false },
  { label: 'Contact', href: '/#contact', isAnchor: true },
  { label: 'Privacy Policy', href: '/privacy', isAnchor: false },
  { label: 'Terms of Service', href: '/terms', isAnchor: false },
]

export default function Footer() {
  return (
    <footer className="border-t border-white/5 bg-base">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          {/* Logo & Tagline */}
          <div>
            <Link to="/" className="inline-flex items-center no-underline mb-4">
              <img src="/logo-wordmark.svg" alt="Locally" className="h-10 w-auto" />
            </Link>
            <p className="text-text-muted text-sm leading-relaxed">
              AI-powered travel planning with personalized itineraries, walking routes, and accommodation recommendations.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="text-white font-semibold text-sm uppercase tracking-wider mb-4">Product</h4>
            <ul className="space-y-3 list-none p-0 m-0">
              {PRODUCT_LINKS.map((link) => (
                <li key={link.label}>
                  {link.isAnchor ? (
                    <a href={link.href} className="text-text-muted hover:text-white text-sm transition-colors no-underline">
                      {link.label}
                    </a>
                  ) : (
                    <Link to={link.href} className="text-text-muted hover:text-white text-sm transition-colors no-underline">
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-white font-semibold text-sm uppercase tracking-wider mb-4">Company</h4>
            <ul className="space-y-3 list-none p-0 m-0">
              {COMPANY_LINKS.map((link) => (
                <li key={link.label}>
                  {link.isAnchor ? (
                    <a href={link.href} className="text-text-muted hover:text-white text-sm transition-colors no-underline">
                      {link.label}
                    </a>
                  ) : (
                    <Link to={link.href} className="text-text-muted hover:text-white text-sm transition-colors no-underline">
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>


        </div>

        {/* Bottom */}
        <div className="mt-12 pt-8 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-text-muted text-xs">
            &copy; {new Date().getFullYear()} BUDOVSKY ONLINE - FZCO. All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-text-muted text-xs">
            <Link to="/privacy" className="hover:text-white transition-colors no-underline">Privacy</Link>
            <Link to="/terms" className="hover:text-white transition-colors no-underline">Terms</Link>
          </div>
        </div>
      </div>
    </footer>
  )
}
