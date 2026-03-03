import { useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import LoginModal from './components/auth/LoginModal'
import LandingPage from './pages/LandingPage'
import PlanTripPage from './pages/PlanTripPage'
import LoadingPage from './pages/LoadingPage'
import ItineraryPage from './pages/ItineraryPage'
import MyTripsPage from './pages/MyTripsPage'
import PrivacyPage from './pages/PrivacyPage'
import TermsPage from './pages/TermsPage'
import AboutPage from './pages/AboutPage'

export default function App() {
  const restoreSession = useAuthStore((s) => s.restoreSession)

  useEffect(() => {
    restoreSession()
  }, [restoreSession])

  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/plan" element={<PlanTripPage />} />
        <Route path="/plan/loading/:tripId" element={<LoadingPage />} />
        <Route path="/itinerary/:tripId" element={<ItineraryPage />} />
        <Route path="/trips" element={<MyTripsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
      <LoginModal />
    </>
  )
}
