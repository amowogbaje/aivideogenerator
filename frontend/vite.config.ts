/// <reference types="vitest" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API (and generated media) live on :8000; proxying keeps the browser on one origin so there's no CORS to configure.
const backend = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  // `npm run test:e2e` drives the real UI against a running backend (E2E_BACKEND, default http://127.0.0.1:8000).
  test: { environment: 'jsdom', testTimeout: 300_000, hookTimeout: 60_000 },
  server: { host: true, port: 5173, proxy: { '/api': backend, '/media': backend } },
})
