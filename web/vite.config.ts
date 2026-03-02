import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')

  return {
    envDir: '..',
    define: {
      'import.meta.env.VITE_GOOGLE_CLIENT_ID': JSON.stringify(
        env.VITE_GOOGLE_CLIENT_ID || env.GOOGLE_CLIENT_ID_WEB || '',
      ),
      'import.meta.env.VITE_GOOGLE_MAPS_API_KEY': JSON.stringify(
        env.VITE_GOOGLE_MAPS_API_KEY || env.GOOGLE_MAPS_API_KEY || '',
      ),
    },
    plugins: [react(), tailwindcss()],
  }
})
