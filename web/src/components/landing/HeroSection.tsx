import { Link } from 'react-router-dom'
import { ArrowRight, Clock3, Compass, MapPin, Sparkles, Star } from 'lucide-react'

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      {/* Large orange sweeping curve — signature hero background */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Main orange curve */}
        <svg
          className="absolute top-0 right-0 w-[120%] h-[90%] opacity-90"
          viewBox="0 0 1200 800"
          fill="none"
          preserveAspectRatio="xMaxYMin slice"
        >
          <defs>
            <linearGradient id="hero-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#f97a1f" stopOpacity="0.85" />
              <stop offset="50%" stopColor="#e8642e" stopOpacity="0.6" />
              <stop offset="100%" stopColor="#c84a20" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          <path
            d="M500,0 L1200,0 L1200,600 C1100,650 900,700 700,600 C500,500 400,350 350,250 C300,150 350,50 500,0 Z"
            fill="url(#hero-gradient)"
          />
        </svg>

        {/* Warm radial glow behind the orange curve */}
        <div className="absolute top-0 right-0 w-[80%] h-[70%] bg-[radial-gradient(ellipse_at_70%_30%,rgba(249,122,31,0.15)_0%,transparent_60%)]" />

        {/* Soft bottom fade to merge with rest of page */}
        <div className="absolute bottom-0 left-0 right-0 h-48 bg-gradient-to-t from-[rgb(30,25,20)] to-transparent" />
      </div>

      <div className="max-w-7xl mx-auto px-6 pt-24 pb-16 w-full relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-12 items-center">
          {/* Left Content */}
          <div className="lg:col-span-3 space-y-6">
            <span className="inline-block text-primary text-xs font-semibold uppercase tracking-widest bg-primary/10 backdrop-blur-sm px-4 py-1.5 rounded-full border border-primary/20">
              AI-Powered Travel Planning
            </span>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight">
              Plan Your
              <br />
              Perfect Trip
              <br />
              <span className="text-primary">with AI</span>
            </h1>

            <p className="text-white/70 text-lg max-w-lg leading-relaxed">
              Experience the future of travel with personalized itineraries built in seconds.
              Sophisticated algorithms meeting luxury exploration.
            </p>

            <div className="flex flex-col sm:flex-row items-start gap-4 pt-2">
              <Link
                to="/plan"
                className="bg-primary hover:bg-primary-hover text-white font-semibold px-8 py-4 rounded-xl text-lg transition-all hover:shadow-lg hover:shadow-primary/25 no-underline"
              >
                Start Planning — It's Free
              </Link>
            </div>
            <p className="text-white/40 text-sm">No credit card required.</p>
          </div>

          {/* Right Preview Card */}
          <div className="lg:col-span-2 relative hidden lg:block">
            <div className="relative">
              <div className="absolute -left-4 top-12 z-10 rounded-2xl border border-white/10 bg-black/30 px-4 py-3 backdrop-blur-xl shadow-2xl shadow-black/30">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-white/40">Locally AI</p>
                    <p className="text-sm font-semibold text-white">A route built around your pace</p>
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-black/25 p-4 shadow-[0_32px_80px_rgba(0,0,0,0.32)] backdrop-blur-2xl transition-transform duration-500 hover:-translate-y-1">
                <div className="rounded-[1.7rem] border border-white/8 bg-[linear-gradient(180deg,rgba(17,13,11,0.92)_0%,rgba(28,19,15,0.88)_100%)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.2em] text-white/35">Route Preview</p>
                      <h3 className="mt-1 text-lg font-semibold text-white">Evening in Istanbul</h3>
                    </div>
                    <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-white/65">
                      3 stops
                    </div>
                  </div>

                  <div className="relative mt-4 overflow-hidden rounded-[1.35rem] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(247,107,46,0.16),transparent_55%),linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.02))] px-4 pb-4 pt-3">
                    <div className="absolute inset-0 opacity-20" style={{
                      backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.18) 1px, transparent 0)',
                      backgroundSize: '30px 30px',
                    }} />

                    <div className="relative flex items-center justify-between text-xs text-white/50">
                      <div className="inline-flex items-center gap-2 rounded-full bg-white/6 px-3 py-1.5">
                        <Compass className="h-3.5 w-3.5 text-primary" />
                        Interactive route
                      </div>
                      <div className="inline-flex items-center gap-2 rounded-full bg-primary/12 px-3 py-1.5 text-primary">
                        <Clock3 className="h-3.5 w-3.5" />
                        38 min walk
                      </div>
                    </div>

                    <div className="relative mt-4 h-44 overflow-hidden rounded-[1.1rem] border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))]">
                      <svg
                        className="absolute inset-0 h-full w-full"
                        viewBox="0 0 360 220"
                        fill="none"
                        preserveAspectRatio="none"
                      >
                        <path
                          d="M44 154C72 145 86 112 120 106C154 100 171 131 202 128C233 125 249 88 279 76C299 68 318 73 336 92"
                          stroke="rgba(247,107,46,0.92)"
                          strokeWidth="6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M48 160C78 152 100 118 127 96C147 80 164 68 190 71"
                          stroke="rgba(255,255,255,0.15)"
                          strokeWidth="2.5"
                          strokeDasharray="8 8"
                          strokeLinecap="round"
                        />
                      </svg>

                      <div className="absolute left-[12%] top-[64%] h-3 w-3 rounded-full bg-primary ring-4 ring-primary/15" />
                      <div className="absolute left-[43%] top-[46%] h-3 w-3 rounded-full bg-[#ffb066] ring-4 ring-[#ffb066]/10" />
                      <div className="absolute right-[18%] top-[30%] h-3 w-3 rounded-full bg-white ring-4 ring-white/10" />

                      <div className="absolute left-4 bottom-4 rounded-2xl border border-white/10 bg-black/45 px-4 py-3 backdrop-blur-xl">
                        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-white/35">
                          <MapPin className="h-3.5 w-3.5 text-primary" />
                          Best sequence
                        </div>
                        <p className="mt-1 text-sm font-semibold text-white">Sunset views, dinner, waterfront walk</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 space-y-2.5">
                    {[
                      { time: '18:30', name: 'Galata Tower Viewpoint', meta: 'Start here', color: 'bg-primary' },
                      { time: '20:00', name: 'Dinner in Karakoy', meta: '5 min away', color: 'bg-[#ffb066]' },
                      { time: '21:30', name: 'Bosphorus promenade', meta: 'Golden finish', color: 'bg-white/80' },
                    ].map((item) => (
                      <div
                        key={item.name}
                        className="flex items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.04] px-3 py-3"
                      >
                        <div className={`h-9 w-1.5 rounded-full ${item.color}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-white/35">
                            <span>{item.time}</span>
                            <span className="h-1 w-1 rounded-full bg-white/20" />
                            <span>{item.meta}</span>
                          </div>
                          <p className="mt-1 truncate text-sm font-semibold text-white">{item.name}</p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-white/20" />
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 flex items-center justify-between rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-white/60">
                      <Star className="h-4 w-4 fill-primary text-primary" />
                      <span>Balanced for mood, distance, and timing</span>
                    </div>
                    <div className="rounded-full bg-primary/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                      Route-first
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
