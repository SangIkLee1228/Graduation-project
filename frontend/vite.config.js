import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const { VITE_API_TARGET } = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react()],
    server: {
      proxy: { '/api': VITE_API_TARGET || 'http://127.0.0.1:8000' },
    },
  }
})
