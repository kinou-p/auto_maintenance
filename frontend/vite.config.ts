import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8800',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8800',
        ws: true,
      },
      '/static': {
        target: 'http://localhost:8800',
        changeOrigin: true,
      },
    },
  },
})
