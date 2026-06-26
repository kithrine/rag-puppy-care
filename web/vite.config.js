import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In dev we run two servers: Vite (5173) for the UI and FastAPI (8000) for the
// API. The proxy forwards any /api/* request from the Vite origin to FastAPI, so
// the frontend can call the SAME relative '/api/ask' in both dev and prod (in
// prod FastAPI serves the built UI and the API itself). No CORS, no env switch.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
