import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
  server: {
    port: 5173,
    proxy: {
      '/query':    'http://localhost:8000',
      '/health':   'http://localhost:8000',
      '/repos':    'http://localhost:8000',
      '/feedback': 'http://localhost:8000',
      '/history':  'http://localhost:8000',

    },
  },
})

