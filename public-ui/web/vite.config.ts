/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // 5174 so the admin UI (5173) and this can run side by side
    port: 5174,
    // WSL /mnt/c file watching is unreliable; enable polling when needed
    watch: process.env.VITE_WSL_POLLING === '1' ? { usePolling: true } : undefined,
    proxy: {
      '/api': 'http://127.0.0.1:7072',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
