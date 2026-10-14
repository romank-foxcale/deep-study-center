import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend (`dsc serve`, port 8000) owns all state; the dev server proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
