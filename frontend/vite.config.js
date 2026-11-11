import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, API calls go to the FastAPI server on :8000. In production FastAPI serves dist/ itself.
const api = 'http://127.0.0.1:8000'
const paths = ['/teams', '/checks', '/jobs', '/plugins', '/features', '/media', '/posts', '/health', '/docs', '/openapi.json']
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: Object.fromEntries(paths.map(p => [p, api])) },
})
