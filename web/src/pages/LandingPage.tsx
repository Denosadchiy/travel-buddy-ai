import Header from '../components/layout/Header'
import Footer from '../components/layout/Footer'
import HeroSection from '../components/landing/HeroSection'
import HowItWorks from '../components/landing/HowItWorks'
import FeaturesSection from '../components/landing/FeaturesSection'
import PhilosophySection from '../components/landing/PhilosophySection'
import ContactSection from '../components/landing/ContactSection'

export default function LandingPage() {
  return (
    <div className="min-h-screen relative bg-warm-gradient bg-warm-glow bg-noise">
      <Header />
      <main className="relative z-[1]">
        <HeroSection />
        <HowItWorks />
        <FeaturesSection />
        <PhilosophySection />
        <ContactSection />
      </main>
      <Footer />
    </div>
  )
}
