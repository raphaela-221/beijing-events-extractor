import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // /api 与 /preview 走后端；SSE 由同一代理透传（http-proxy 默认不缓冲）
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/preview': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
