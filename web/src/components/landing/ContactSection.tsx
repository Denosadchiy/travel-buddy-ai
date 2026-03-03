import { useState } from 'react'
import { Send } from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function ContactSection() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !email.trim() || !message.trim()) return

    setStatus('sending')
    try {
      const res = await fetch(`${API_BASE_URL}/api/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, message }),
      })
      if (!res.ok) throw new Error()
      setStatus('sent')
      setName('')
      setEmail('')
      setMessage('')
      setTimeout(() => setStatus('idle'), 4000)
    } catch {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 4000)
    }
  }

  const buttonLabel = {
    idle: 'Send Message',
    sending: 'Sending...',
    sent: 'Message Sent!',
    error: 'Failed to send. Try again.',
  }[status]

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
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Doe"
                  className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-2">Email Address</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jane@example.com"
                  className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-text-secondary mb-2">Message</label>
              <textarea
                rows={4}
                required
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="How can we help you?"
                className="w-full bg-white/5 border border-border-default rounded-xl px-4 py-3 text-white placeholder-text-muted focus:outline-none focus:border-primary transition-colors resize-none"
              />
            </div>

            <button
              type="submit"
              disabled={status === 'sending'}
              className="w-full bg-primary hover:bg-primary-hover disabled:opacity-50 text-white font-semibold py-3.5 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              <Send className="w-4 h-4" />
              {buttonLabel}
            </button>
          </form>
        </div>
      </div>
    </section>
  )
}
