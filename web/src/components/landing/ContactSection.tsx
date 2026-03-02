import { useState } from 'react'
import { Send } from 'lucide-react'

export default function ContactSection() {
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Frontend-only: just show success
    setSubmitted(true)
    setTimeout(() => setSubmitted(false), 3000)
  }

  return (
    <section id="contact" className="py-24">
      <div className="max-w-3xl mx-auto px-6">
        <div className="bg-surface border border-border-default rounded-2xl p-8 sm:p-12">
          <div className="text-center mb-10">
            <h2 className="text-3xl font-bold mb-3">Get in Touch</h2>
            <p className="text-text-secondary">
              Have questions or enterprise inquiries? Our team is here to help.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm text-text-secondary mb-2">Full Name</label>
                <input
                  type="text"
                  placeholder="Jane Doe"
                  className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-2">Email Address</label>
                <input
                  type="email"
                  placeholder="jane@example.com"
                  className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-text-secondary mb-2">Message</label>
              <textarea
                rows={4}
                placeholder="How can we help you?"
                className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors resize-none"
              />
            </div>

            <button
              type="submit"
              className="w-full bg-primary hover:bg-primary-hover text-white font-semibold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              <Send className="w-4 h-4" />
              {submitted ? 'Message Sent!' : 'Send Message'}
            </button>
          </form>
        </div>
      </div>
    </section>
  )
}
