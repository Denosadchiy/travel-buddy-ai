import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import App from './App'
import { GOOGLE_CLIENT_ID, hasGoogleClientId } from './lib/env'

const app = (
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
)

createRoot(document.getElementById('root')!).render(
  hasGoogleClientId ? (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID} locale="en">
      {app}
    </GoogleOAuthProvider>
  ) : (
    app
  ),
)
