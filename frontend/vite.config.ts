import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env variables (including VITE_API_URL) so they are available to the config
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    // VITE_API_URL is automatically exposed to the client via import.meta.env
    // because it is prefixed with VITE_. We reference it here explicitly so
    // the dev server is aware of it when computing the proxy target.
    define: {
      // No explicit define needed — Vite auto-exposes all VITE_* env vars.
    },
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_URL ?? 'http://localhost:8000',
          changeOrigin: true,
          // Do NOT rewrite — keeps /api prefix so FastAPI receives the full path
        },
      },
    },
  }
})
