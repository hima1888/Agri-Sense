import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// findBy*/waitFor default to 1 s, which is too tight when all test files run in parallel on a busy machine.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom lacks these browser APIs used by the ambient background and Framer Motion.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
})

class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}
Object.defineProperty(window, 'IntersectionObserver', { writable: true, value: IO })

HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']

// Load pages eagerly in unit tests (see src/test/eager-pages.ts). The 3D twin stays lazy as before Phase 19.
vi.mock('@/app/lazy-pages', async () => ({
  ...(await import('@/test/eager-pages')),
  TwinPage: (await vi.importActual<typeof import('@/app/lazy-pages')>('@/app/lazy-pages')).TwinPage,
}))
