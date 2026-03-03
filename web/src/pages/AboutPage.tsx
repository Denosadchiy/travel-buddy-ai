import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-base flex flex-col">
      <Header />
      <main className="flex-1 pt-24 pb-16 px-6">
        <article className="max-w-3xl mx-auto prose-invert">
          <h1 className="text-3xl font-bold text-white mb-2">About Us</h1>
          <p className="text-text-muted text-sm mb-8">Travel planning, reimagined with AI</p>

          <div className="space-y-8 text-text-secondary text-sm leading-relaxed">
            <section>
              <h2 className="text-lg font-semibold text-white mb-3">Our Mission</h2>
              <p>
                Locally is an AI-powered travel planning platform that creates personalized itineraries tailored to your interests, pace, and budget. We believe every traveler deserves a unique experience — not a generic checklist of tourist spots.
              </p>
              <p className="mt-2">
                Our AI analyzes thousands of places, reviews, and local insights to build optimized walking routes, recommend authentic restaurants, and find the best accommodations for your trip.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">What We Offer</h2>
              <ul className="list-disc list-inside space-y-2">
                <li>AI-generated personalized travel itineraries</li>
                <li>Optimized walking routes with real-time navigation</li>
                <li>Smart accommodation recommendations via Booking.com</li>
                <li>Local insights and hidden gems powered by AI</li>
                <li>Weather-aware trip planning</li>
                <li>Save and share your travel plans</li>
              </ul>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">Company Information</h2>
              <div className="bg-white/5 rounded-lg p-6 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">Legal Name</p>
                    <p className="text-white font-medium">BUDOVSKY ONLINE - FZCO</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">Address</p>
                    <p className="text-white">Dubai Silicon Oasis</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">City</p>
                    <p className="text-white">Dubai</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">Country</p>
                    <p className="text-white">United Arab Emirates</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">Postal Code</p>
                    <p className="text-white">00000</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wider mb-1">Phone</p>
                    <p>
                      <a href="tel:+971521173919" className="text-primary hover:underline">+971 52 117 3919</a>
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">Contact Us</h2>
              <p>
                Have questions, feedback, or partnership inquiries? We'd love to hear from you.
              </p>
              <ul className="list-none mt-3 space-y-2">
                <li>
                  Email:{' '}
                  <a href="mailto:locally.office@gmail.com" className="text-primary hover:underline">locally.office@gmail.com</a>
                </li>
                <li>
                  Phone:{' '}
                  <a href="tel:+971521173919" className="text-primary hover:underline">+971 52 117 3919</a>
                </li>
              </ul>
            </section>
          </div>
        </article>
      </main>
      <Footer />
    </div>
  )
}
