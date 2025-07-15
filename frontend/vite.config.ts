import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Allow access from the custom domain
    allowedHosts: [
      'localhost',
      '127.0.0.1',
      process.env.VITE_FRONTEND_DOMAIN || 'your-domain.com'
    ],
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8080',
        changeOrigin: true,
        secure: false, // Allow self-signed certificates in development
      },
    },
    hmr: {
      }
    },
})
