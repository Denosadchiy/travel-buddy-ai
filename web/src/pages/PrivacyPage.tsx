import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-base flex flex-col">
      <Header />
      <main className="flex-1 pt-24 pb-16 px-6">
        <article className="max-w-3xl mx-auto prose-invert">
          <h1 className="text-3xl font-bold text-white mb-2">Privacy Policy</h1>
          <p className="text-text-muted text-sm mb-8">Last updated: March 1, 2025</p>

          <div className="space-y-6 text-text-secondary text-sm leading-relaxed">
            <section>
              <h2 className="text-lg font-semibold text-white mb-3">Data Controller</h2>
              <p>
                The data controller responsible for your personal data is <strong className="text-white">BUDOVSKY ONLINE - FZCO</strong>, registered at Dubai Silicon Oasis, Dubai, United Arab Emirates. Phone: <a href="tel:+971521173919" className="text-primary hover:underline">+971 52 117 3919</a>. Email: <a href="mailto:konkin.g@yandex.ru" className="text-primary hover:underline">konkin.g@yandex.ru</a>.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">1. Information We Collect</h2>
              <p>
                When you use Locally, we may collect the following types of information:
              </p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li><strong className="text-white">Account Information:</strong> email address, display name when you create an account.</li>
                <li><strong className="text-white">Trip Data:</strong> destinations, travel dates, preferences, and itineraries you create.</li>
                <li><strong className="text-white">Device Information:</strong> anonymous device identifiers for guest functionality.</li>
                <li><strong className="text-white">Usage Data:</strong> pages visited, features used, and interaction patterns to improve our service.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">2. How We Use Your Information</h2>
              <ul className="list-disc list-inside space-y-1">
                <li>Generate personalized travel itineraries using AI.</li>
                <li>Save and retrieve your travel plans.</li>
                <li>Improve our algorithms and user experience.</li>
                <li>Communicate service updates and respond to inquiries.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">3. Third-Party Services</h2>
              <p>We use the following third-party services to provide our functionality:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li><strong className="text-white">Google Maps Platform:</strong> for location data, maps, and place information. Subject to <a href="https://policies.google.com/privacy" className="text-primary hover:underline" target="_blank" rel="noopener noreferrer">Google's Privacy Policy</a>.</li>
                <li><strong className="text-white">Booking.com:</strong> for accommodation search and booking. Subject to Booking.com's Privacy Policy.</li>
                <li><strong className="text-white">AI Providers:</strong> for itinerary generation. Your trip preferences are processed to create personalized recommendations.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">4. Data Storage and Security</h2>
              <p>
                Your data is stored securely using industry-standard encryption. We retain your account and trip data for as long as your account is active. You may request deletion of your data at any time by contacting us.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">5. Cookies</h2>
              <p>
                We use essential cookies and local storage to maintain your session, store authentication tokens, and remember your preferences. We do not use third-party tracking cookies for advertising purposes.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">6. Your Rights</h2>
              <p>You have the right to:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Access the personal data we hold about you.</li>
                <li>Request correction of inaccurate data.</li>
                <li>Request deletion of your data.</li>
                <li>Withdraw consent for data processing.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">7. Changes to This Policy</h2>
              <p>
                We may update this Privacy Policy from time to time. We will notify you of significant changes via email or a prominent notice on our website.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-3">8. Contact Us</h2>
              <p>If you have questions about this Privacy Policy, please contact us:</p>
              <ul className="list-none mt-2 space-y-1">
                <li><strong className="text-white">BUDOVSKY ONLINE - FZCO</strong></li>
                <li>Dubai Silicon Oasis, Dubai, United Arab Emirates</li>
                <li>Phone: <a href="tel:+971521173919" className="text-primary hover:underline">+971 52 117 3919</a></li>
                <li>Email: <a href="mailto:konkin.g@yandex.ru" className="text-primary hover:underline">konkin.g@yandex.ru</a></li>
              </ul>
            </section>
          </div>
        </article>
      </main>
      <Footer />
    </div>
  )
}
