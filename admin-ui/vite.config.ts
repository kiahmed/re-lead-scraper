/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // WSL /mnt/c file watching is unreliable; enable polling when needed
    watch: process.env.VITE_WSL_POLLING === '1' ? { usePolling: true } : undefined,
    proxy: {
      '/api': 'http://127.0.0.1:7071',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
