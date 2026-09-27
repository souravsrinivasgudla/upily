import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // A production build without the backend URL deploys a site whose API calls all
  // hit index.html. Fail loudly instead (set ALLOW_RELATIVE_API=1 to build anyway,
  // e.g. when the API is served from the same origin).
  if (command === 'build' && !env.VITE_API_URL && !env.ALLOW_RELATIVE_API) {
    throw new Error(
      'VITE_API_URL is not set. Set it to your backend origin (e.g. https://upily-api.onrender.com) ' +
      'in Vercel → Settings → Environment Variables, or set ALLOW_RELATIVE_API=1.'
    )
  }

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/api': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
  }
})
