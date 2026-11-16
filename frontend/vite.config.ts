/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // In development, /api is proxied to the FastAPI backend so the browser
    // talks to a single origin. In production, VITE_API_BASE_URL is used.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            // three.js / R3F are deliberately NOT grouped here: left alone, they stay in the
            // lazily-loaded twin chunk instead of being preloaded on every page.
            const THREE_D = /[/\\](three|@react-three|three-stdlib|three-mesh-bvh|troika-[^/\\]+|maath|camera-controls|meshline)[/\\]/
            if (THREE_D.test(id)) return undefined
            if (/recharts|d3-/.test(id)) return 'vendor-charts'
            if (/framer-motion|motion-/.test(id)) return 'vendor-motion'
            if (/react|scheduler/.test(id)) return 'vendor-react'
          }
          return undefined
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Playwright specs (e2e/) run with `npm run test:e2e`, not Vitest.
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    css: false,
    // Multi-page flows (sign-in, redirects) can exceed 5 s when all files run in parallel on a busy machine.
    testTimeout: 15_000,
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      // Scene.tsx needs WebGL (not available in jsdom); the Playwright E2E suite covers the twin instead.
      exclude: ['src/**/*.test.*', 'src/test/**', 'src/main.tsx', 'src/features/twin/Scene.tsx', 'src/**/*.d.ts'],
      reporter: ['text-summary', 'html'],
      // Floors (measured in Phase 18, kept a little below so normal changes do not fail CI).
      thresholds: { lines: 80, statements: 78, functions: 75, branches: 65 },
    },
  },
})
