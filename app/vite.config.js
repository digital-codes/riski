import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // dev proxy: frontend calls /api/... (same shape as production, where
    // the API is served under $HOMEURL/api/...); vite forwards to the
    // local FastAPI server (uvicorn src.apiServer:app --port 8000).
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
